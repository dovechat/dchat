import uuid
from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from models.messages import Message
from repo.base import BaseRepository

import logging
log = logging.getLogger("uvicorn.error")


class MessageRepository(BaseRepository[Message]):
    """Repository for message operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def get_conversation_messages(
            self,
            conversation_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> List[Message]:
        """Get messages for conversation"""
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .options(joinedload(Message.user))
            .order_by(self.model.created_at)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        res = list(result.scalars().all())
        return res

    async def get_last_message(
            self,
            conversation_id: uuid.UUID,
    ) -> Message:
        """Get messages for conversation"""
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .order_by(desc(self.model.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_unread_count(
            self,
            conversation_id: uuid.UUID
    ) -> int:
        """Count unread messages in conversation"""
        stmt = select(func.count()).where(
            self.model.conversation_id == conversation_id,
            self.model.status == "sent",
            self.model.direction == "incoming"
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
    
    
    async def create_message(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        direction: str,
        text: Optional[str] = None,
        channel_msg_id: Optional[str] = None,
        media_id: Optional[str] = None,
        raw_content: Optional[dict] = None
    ) -> Message:
        """Create new message"""
        return await self.create(
            user_id=user_id,
            conversation_id=conversation_id,
            channel_msg_id=channel_msg_id,
            direction=direction,
            text=text,
            media_id=media_id,
            raw_content=raw_content or {}
        )
    
    async def set_message_status(self, id: str, status: str):
        """Update status to active using base update logic"""
        message = await self.get_by_id(id)
        if message:
            return await self.update(message, status=status)

    async def get_message_by_channel_msg_id(self, id: str):
        msgs = await self.get_multi(
            filters={"channel_msg_id": id},
            limit=1
        )
        msg = msgs[0] if msgs else None
        return msg