import httpx
import json
import uuid
from typing import List, Optional
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.chat_schemas import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    ConversationListResponse
)
from app.schemas.telegram_schemas import KafkaEvent
from app.services.websocket_manager import manager
from app.core.kafka_producer import kafka_producer
from core.dependencies import get_current_user
from infra.crypto import decrypt
from models.messages import Conversation, MessageDirection
from schemas.auth_schemas import UserContext

import logging
log = logging.getLogger("uvicorn.error")

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conv_repo = ChatRepository(db)
        self.msg_repo = MessageRepository(db)

    async def get_conversations(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> List[ConversationListResponse]:
        """Get conversations list with last message for tenant"""
        rows = await self.conv_repo.get_conversations_with_stats(tenant_id, skip, limit)

        conversations = []
        for conv, unread_count, last_msg_at in rows:
            last_msg = None
            if last_msg_at:
                last_msg_obj = await self.msg_repo.get_last_message(conv.id)
                if last_msg_obj:
                    last_msg = MessageResponse.model_validate(last_msg_obj)

            conversations.append(ConversationListResponse(
                **conv.__dict__,
                unread_count=unread_count,
                last_message=last_msg
            ))

        return conversations

    async def get_conversation(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID
    ) -> Optional[ConversationResponse]:
        """Get conversation with all messages"""
        conversation = await self.conv_repo.get_conversation_with_messages(conversation_id)

        if not conversation:
            return None

        messages = await self.msg_repo.get_conversation_messages(
            conversation_id, skip=0, limit=1000
        )

        my_phone = await self.conv_repo.get_line_phone_by_conversation(conversation_id)

        return ConversationResponse(
            **conversation.__dict__,
            messages=[MessageResponse.model_validate(msg) for msg in messages],
            my_phone=my_phone,
        )

    async def get_messages(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> List[MessageResponse]:
        """Get messages for conversation"""
        # Verify access
        conv = await self.conv_repo.get_conversation_with_messages(conversation_id)
        if not conv:
            return []

        messages = await self.msg_repo.get_conversation_messages(
            conversation_id, skip, limit
        )

        result = []
        for msg in messages:
            msg_dict = msg.__dict__
            if msg.user:
                msg_dict['user_email'] = msg.user.email
                msg_dict['user_full_name'] = msg.user.full_name
            result.append(MessageResponse.model_validate(msg_dict))
        return result


    async def create_conversation(
            self,
            tenant_id: uuid.UUID,
            data: ConversationCreate
    ) -> ConversationResponse:
        """Create new conversation"""
        conversation = await self.conv_repo.create_conversation(
            line_id=data.line_id,
            crm_type=data.crm_type,
            crm_chat_id=data.crm_chat_id,
            client_phone=data.client_phone,
            meta=data.meta
        )

        return ConversationResponse(
            **conversation.__dict__,
            messages=[]
        )
    
    
    async def conv_msg(
        self,
        data: MessageCreate,
        current_user: UserContext = Depends(get_current_user),
    ) -> Conversation:
        # Verify conversation exists and belongs to tenant
        log.info(f"+++++ chat_service ChatService.create_message current_user {current_user}")
        log.info(f"chat_service ChatService.create_message data {data}")
        conv = await self.conv_repo.get_conversation_with_messages(data.conversation_id)
        if not conv:
            raise ValueError("Conversation not found")
        log.info(f"chat_service ChatService.create_message conv {conv}")

        
        message = await self.msg_repo.create_message(
            user_id=current_user.id if data.direction == MessageDirection.outbound else None,
            conversation_id=data.conversation_id,
            channel_msg_id=data.channel_msg_id,
            direction=data.direction,
            text=data.text,
            media_id=data.media_id,
            raw_content=data.raw_content
        )
        await self.db.commit()
        log.info(f"******* message {message}")
        return conv, message


    async def create_msg_tguser(
        self,
        request: Request,
        data: MessageCreate,
        current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new message in conversation"""
        log.info(f"++++++++ **** create_msg_tguser current_user {current_user}")
        listener = request.app.state.listener

        log.info(f"********* data {data}")


        try:
            await listener.send_message_user(
                conversation_id=str(data.conversation_id),
                recipient=data.phone,
                text=data.text
            )
            data.status = "sent"
            # raise Exception("Test retry")
        except Exception as e:
            data.status = "error"
            log.error(f"ERROR: listener.send_message_user has been failed e={e}")

            await kafka_producer.send_event(
                topic='telegram_user_retry',
                event=KafkaEvent(
                    event_id=str(uuid.uuid4()),
                    event_type='message_retry',
                    payload={
                        'message_id': str(data.id),
                        'conversation_id': str(data.conversation_id),
                        'text': data.text
                    },
                    account_phone=data.phone
                )
            )
        finally:
            log.info(f"********* create_msg_tguser data {data} ")
            conv, message = await self.conv_msg(data, current_user)

            await manager.send_new_message(str(data.conversation_id), {
                "id": str(message.id),
                "text": message.text,
                "direction": "outbound",
                "created_at": message.created_at.isoformat(),
                "user_id": str(current_user.id),
                "user_email": current_user.email,
            })

            return MessageResponse.model_validate(message)

    async def create_msg_tgbot(
            self,
            data: MessageCreate,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        log.info(f"\n\n *********** create_msg_tgbot  data {data} \n\n")
        # Получаем bot_token
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        creds_enc = channel_acc.credentials_encrypted["encrypted_data"]
        log.info(f"--------------- creds_enc {type(creds_enc)} {creds_enc}")
        creds_str = decrypt(creds_enc)
        log.info(f"--------------- creds {type(creds_str)} {creds_str}")
        if not channel_acc or 'bot_token' not in creds_str:
            raise ValueError("Bot token not found")
        bot_token = json.loads(creds_str)["bot_token"]

        # Отправка через Bot API
        try:
            # raise Exception("Test retry")
            async with httpx.AsyncClient() as client:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": data.phone,
                    "text": data.text
                }
                await client.post(url, json=payload)
            data.status = "sent"
            log.info(f"\n\n +++++++++++++ create_msg_tgbot async with httpx.AsyncClient data {data}  \n\n")
        except Exception as e:
            data.status = "error"
            log.error(f"Send failed: {e}")
            await kafka_producer.send_event(
                topic='telegram_bot_retry',
                event=KafkaEvent(
                    event_id=str(uuid.uuid4()),
                    event_type='message_retry',
                    payload={
                        'message_id': str(data.id),
                        'conversation_id': str(data.conversation_id),
                        'text': data.text
                    },
                    account_phone=data.phone
                )
            )
        finally:
            # Сохраняем сообщение в БД с нужным статусом
            _, message = await self.conv_msg(data, current_user)

            await manager.send_new_message(str(data.conversation_id), {
                "id": str(message.id),
                "text": message.text,
                "direction": "outbound",
                "created_at": message.created_at.isoformat(),
                "user_id": str(current_user.id),
                "user_email": current_user.email,
            })

            return MessageResponse.model_validate(message)


    async def save_incoming_message(
            self,
            conversation_id: uuid.UUID,
            peer_phone: str,
            event
    ) -> MessageResponse:
        """Сохраняет входящее сообщение из Telegram"""
        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=event.message.text,
            channel_msg_id=str(event.message.id),
            raw_content={
                "phone": peer_phone,
                "date": event.message.date.isoformat()
            }
        )

        try:
            _, message = await self.conv_msg(data)
        except Exception as e:
            log.error(f"save_incoming_message error: {e}", exc_info=True)
            raise

        return MessageResponse.model_validate(message)
