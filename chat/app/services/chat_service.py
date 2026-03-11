import asyncio
import base64
import httpx
import json
import uuid

from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple
from fastapi import Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
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
from app.senders.factory import SenderFactory
from app.services.websocket_manager import manager
from app.core.kafka_producer import kafka_producer
from core.config import settings
from core.dependencies import get_current_user
from infra.crypto import decrypt
from models.messages import Conversation, Message, MessageDirection
from schemas.auth_schemas import UserContext

import logging
log = logging.getLogger("uvicorn.error")

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conv_repo = ChatRepository(db)
        self.msg_repo = MessageRepository(db)
        self.s3_client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )

    async def get_conversations(
            self,
            tenant_id: uuid.UUID,
            line_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> List[ConversationListResponse]:
        """Get conversations list with last message for tenant"""
        rows = await self.conv_repo.get_conversations_with_stats(tenant_id, line_id, skip, limit)

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
            log.info(f"========  msg.raw_content {msg.raw_content}")
            if msg.raw_content and msg.raw_content.get("file_name") is not None:
                msg_dict['file_name'] = msg.raw_content.get("file_name")
            if msg.user:
                msg_dict['user_email'] = msg.user.email
                msg_dict['user_full_name'] = msg.user.full_name
                log.info(f"========  msg_dict['file_name'] {msg_dict.get("file_name") }")
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
    ) -> Tuple[Conversation, Message]:
        # Verify conversation exists and belongs to tenant
        # log.info(f"+++++ chat_service ChatService.create_message current_user {current_user}")
        # log.info(f"chat_service ChatService.create_message data {data}")
        conv = await self.conv_repo.get_conversation_with_messages(data.conversation_id)
        if not conv:
            raise ValueError("Conversation not found")
        # log.info(f"chat_service ChatService.create_message conv {conv}")

        
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
        # log.info(f"******* message {message}")
        return conv, message

    async def _finalize_message(
            self,
            message,
            conversation_id: uuid.UUID,
            channel_type: str,
            data: MessageCreate,
            current_user: UserContext,
            success: bool = True,
            channel_msg_id: str = None,
            raw_content: dict = None,
            error: Exception = None,
    ):
        """Общая обработка результата отправки"""

        # 1. Вебсокет о новом сообщении (всегда)

        if success:
            # 2. Обновляем message (channel_msg_id, raw_content)
            if channel_msg_id or raw_content:
                await self.msg_repo.update(
                    message,
                    channel_msg_id=channel_msg_id,
                    raw_content=raw_content
                )
            
            log.info(f"=============== ChatServcie._finalize_message data.raw_content {data.raw_content}")
            # 3. Статус delivered
            await manager.send_message_status(str(conversation_id), {
                "message_id": str(message.id),
                "status": "delivered",
                "mime_type": data.raw_content.get("mime_type")
            })
        else:
            # 4. Ошибка -> в Kafka (для каждого канала своё)
            topic_map = {
                "telegram_user": "telegram_user_retry",
                "telegram_bot": "telegram_bot_retry",
                "whatsapp_green": "whatsapp_green_retry",
            }

            topic = topic_map.get(channel_type, "default_retry")

            await kafka_producer.send_event(
                topic=topic,
                event=KafkaEvent(
                    event_id=str(uuid.uuid4()),
                    event_type='message_retry',
                    payload={
                        'message_id': str(data.id),
                        'conversation_id': str(conversation_id),
                        'text': data.text,
                        'media_id': data.media_id  # если есть
                    },
                    account_phone=data.phone
                )
            )

    async def _save_uploaded_file(self, file: UploadFile, media_id: uuid.UUID) -> dict:
        log.info(f"========== ChatService._save_uploaded_file media_id {media_id}")
        file_bytes = await file.read()
        return await self._save_file(file_bytes, media_id, file.filename, file.content_type)

    async def _save_file(self, file_bytes: bytes, media_id: uuid.UUID, filename: str, mime_type: str ) -> dict:
        stream = BytesIO(file_bytes)
        metadata = {
            "filename": filename,
            "content_type": mime_type,
            "size": len(file_bytes)
        }
        self.s3_client.put_object(
            settings.s3_bucket,  # bucket_name
            str(media_id),  # object_name
            stream,  # data
            len(file_bytes),  # length
            content_type=mime_type,
            metadata=metadata,
        )
        return {
            "media_id": media_id,
            "filename": filename,
            "mime_type": mime_type,
            "size": len(file_bytes)
        }

    def clean_raw_content(self, obj):
        """Рекурсивно преобразует все datetime в строки"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return base64.b64encode(obj).decode('ascii')
        elif isinstance(obj, dict):
            return {k: self.clean_raw_content(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.clean_raw_content(i) for i in obj]
        return obj


    async def create_msg_tguser(
        self,
        request: Request,
        data: MessageCreate,
        file: UploadFile | None = None,
        current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new message in conversation"""
        listener = request.app.state.listener

        if file:
            # Сохраняем файл
            file_info = await self._save_uploaded_file(file, data.media_id)
            # log.info(f"File saved: file {file}")
            # log.info(f"File saved: file_info {file_info}")
            data.raw_content["file_name"] = file.filename

        conv, message = await self.conv_msg(data, current_user)

        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media_id": data.media_id,
            "file_name": data.raw_content.get('file_name') if file else None,
            "mime_type": data.raw_content.get('mime_type') if file else None,
        })

        sender = SenderFactory.get_sender("telegram_user")
        sender.set_listener(listener)
        # log.info(f"---------- sender {sender}")
        # log.info(f"---------- sender.listener {sender.listener}")
        # log.info(f"---------- sender.listener.send_message_user {sender.listener.send_message_user}")
        sent = None
        try:
            # log.info(f"\n\n +++++++++++++ ChatService.create_msg_tguser  data {data} message {message}  \n\n")
            sent = await sender.send(data)
            # log.info(f"\n\n +++++++++++++ ChatService.create_msg_tguser file sent {sent} file.filename {file.filename}  \n\n")
            success = True
        except Exception as e:
            log.error(f"ERROR: {e}")
            success = False
        finally:
            raw_content = None
            if sent:
                raw_content = sent.to_dict()
                raw_content = self.clean_raw_content(raw_content)
                if file:
                    raw_content['file_name'] = file.filename

            await self._finalize_message(
                message=message,
                conversation_id=data.conversation_id,
                channel_type="telegram_user",
                data=data,
                current_user=current_user,
                success=success,
                channel_msg_id=str(sent.id) if sent else None,
                raw_content=raw_content
            )

        res = MessageResponse.model_validate(message)
        log.info(f"\n\n ++ ChatService.create_msg_tguser data {data}  \n\n")
        # log.info(f"\n\n ++ ChatService.create_msg_tguser message.raw_content {res.raw_content}  \n\n")
        # log.info(f"\n\n ++ ChatService.create_msg_tguser file_name {res.raw_content.get('file_name')}  \n\n")

        return res

    async def create_msg_tgbot(
            self,
            request: Request,
            data: MessageCreate,
            file: UploadFile | None = None,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        log.info(f"\n\n *********** create_msg_tgbot  data {data} \n\n")

        if file:
            # Сохраняем файл
            file_info = await self._save_uploaded_file(file, data.media_id)
            # log.info(f"File saved: file {file}")
            # log.info(f"File saved: file_info {file_info}")
            data.raw_content["file_name"] = file.filename

        # Сохраняем сообщение в БД
        _, message = await self.conv_msg(data, current_user)

        # Первый пинок (новое сообщение)
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media_id": data.media_id,
            "file_name": data.raw_content.get("file_name") if data.raw_content else None,
            "mime_type": data.raw_content.get("mime_type") if data.raw_content else None
        })

        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        creds_enc = channel_acc.credentials_encrypted["encrypted_data"]
        creds_str = decrypt(creds_enc)
        bot_token = json.loads(creds_str)["bot_token"]

        # Получаем сендер
        sender = SenderFactory.get_sender("telegram_bot")
        sender.set_bot_token(bot_token)

        try:
            # Отправка через сендер
            result = await sender.send(data)
            success = True
            channel_msg_id = str(result.get("message_id")) if result else None
            raw_content = result if result else None
        except Exception as e:
            log.error(f"Send failed: {e}")
            success = False
            channel_msg_id = None
            raw_content = None

        # Финальная обработка
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="telegram_bot",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content=raw_content
        )

        return MessageResponse.model_validate(message)

    async def create_msg_whatsapp_green(
            self,
            data: MessageCreate,
            file: UploadFile | None = None,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new WhatsApp Green message"""
        # Получаем креды линии
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))

        log.info(f"\n\n ************ ChatService.create_msg_whatsapp_green creds {creds} \n\n")

        # Сохраняем сообщение в БД
        conv, message = await self.conv_msg(data, current_user)

        # Отправляем на фронт сразу
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media_id": data.media_id,
        })

        # Отправка через Green API
        sender = SenderFactory.get_sender("whatsapp_green")
        sender.set_creds(creds)
        success = False

        channel_msg_id = None

        try:
            if file:
                file_info = await self._save_uploaded_file(file, data.media_id)
        except Exception as e:
            log.error(f"WhatsApp Green _save_uploaded_file failed: {e}")

        try:
            result = await sender.send(data)
            success = True
            channel_msg_id = result.get("idMessage")
        except Exception as e:
            log.error(f"WhatsApp Green send failed: {e}")
            

        # Финальное обновление
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="whatsapp_green",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content={"file_name": file.filename, "mime_type": file_info['mime_type']} if file else None
        )

        return MessageResponse.model_validate(message)



    async def save_incoming_message(
            self,
            conversation_id: uuid.UUID,
            peer_phone: str,
            event,
            media_id: uuid.UUID = None,
            file_name: str = None,
            mime_type: str = None
    ) -> MessageResponse:
        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=event.message.text if event.message.text else None,
            channel_msg_id=str(event.message.id),
            media_id=str(media_id),
            file_name=file_name,
            mime_type=mime_type,
            raw_content={
                "phone": peer_phone,
                "date": event.message.date.isoformat(),
                "file_name": file_name,
                "mime_type": mime_type
            }
        )

        try:
            _, message = await self.conv_msg(data)
        except Exception as e:
            log.error(f"save_incoming_message error: {e}", exc_info=True)
            raise
        res = MessageResponse.model_validate(message)
        log.error(f"\n\n -*-+-*-+-*-+  MessageResponse res {res} res")
        return res

    async def save_incoming_green(
            self,
            conversation_id: uuid.UUID,
            payload: dict,
            media_id: uuid.UUID | None = None,
            file_name: str | None = None,
            file_url: str | None = None,
            mime_type: str | None = None,
            text: str | None = None,
    ) -> MessageResponse:
        """Сохранить входящее сообщение из WhatsApp Green"""

        # log.info(f"\n\n --------- ChatService.save_incoming_green conversation_id {conversation_id}  media_id {media_id}  file_name {file_name} file_url {file_url} mime_type {mime_type}  \n\n")
        # log.info(f"\n\n --------- ChatService.save_incoming_green text {text}")

        if file_url:
            async with httpx.AsyncClient() as client:
                res = await client.get(file_url)
                if res:
                    file_bytes = res.content
                    await self._save_file(file_bytes, media_id, file_name, mime_type)

        raw_content = payload
        if mime_type:
            raw_content["mime_type"] = mime_type

        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text,
            channel_msg_id=payload.get("idMessage"),
            media_id=str(media_id) if media_id else None,
            file_name=file_name,
            mime_type=mime_type,
            raw_content=raw_content
        )

        _, message = await self.conv_msg(data)
        return MessageResponse.model_validate(message)

    
    async def upload_file(self, file: UploadFile, media_id: uuid.UUID) -> dict:
        """Upload file to S3"""
        # 1. Читаем файл
        content = await file.read()
    
        # 2. Генерируем метаданные
        metadata = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        }
    
        # 3. Сохраняем в S3 под ключом = media_id
        await self.s3_client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=str(media_id),
            Body=content,
            Metadata=metadata,
            ContentType=file.content_type
        )
    
        # 4. Возвращаем информацию
        return {
            "media_id": media_id,
            "filename": file.filename,
            "mime_type": file.content_type,
            "size": len(content)
        }