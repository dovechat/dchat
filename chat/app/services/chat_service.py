import uuid
from typing import List, Optional
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
from app.core.kafka_producer import kafka_producer

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
        conversation = await self.conv_repo.get_conversation_with_messages(
            conversation_id, tenant_id
        )

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
        conv = await self.conv_repo.get_conversation_with_messages(
            conversation_id, tenant_id
        )
        if not conv:
            return []

        messages = await self.msg_repo.get_conversation_messages(
            conversation_id, skip, limit
        )

        return [MessageResponse.model_validate(msg) for msg in messages]


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
    
    
    async def create_message(
            self,
            tenant_id: uuid.UUID,
            data: MessageCreate
    ) -> MessageResponse:
        """Create new message in conversation"""
        # Verify conversation exists and belongs to tenant
        log.info(f"chat_service ChatService.create_message data {data}")
        conv = await self.conv_repo.get_conversation_with_messages(
            data.conversation_id, tenant_id
        )
        if not conv:
            raise ValueError("Conversation not found")
        log.info(f"chat_service ChatService.create_message conv {conv}")

        message = await self.msg_repo.create_message(
            conversation_id=data.conversation_id,
            channel_msg_id=data.channel_msg_id,
            direction=data.direction,
            text=data.text,
            media_id=data.media_id,
            raw_content=data.raw_content
        )

        log.info(f"******* message {message}")

        from app.consumers.telegram_listener import listener

        # вместо kafka_producer.send_event
        await listener.send_message(
            conversation_id=str(data.conversation_id),
            recipient=data.phone,
            text=data.text
        )

        return MessageResponse.model_validate(message)