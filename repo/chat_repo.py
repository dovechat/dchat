import uuid
from typing import List, Optional
from sqlalchemy import desc, func, and_, select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import ChannelAccount, Line
from models.messages import Conversation, Message
from repo.base import BaseRepository

import logging
log = logging.getLogger(__name__)

class ChatRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)  # ← передать model и session

    async def get_conversations_by_line(
        self,
        line_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[Conversation]:
        """Get conversations for specific line"""
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"line_id": line_id},
            order_by="-updated_at"
        )


    async def get_channel_acc_by_conversation(
        self,
        conversation_id: uuid.UUID
    ) -> Optional[str]:
        """Get session_string from channel_account by conversation_id"""
        stmt = (
            select(ChannelAccount)
            .join(Conversation, Conversation.line_id == ChannelAccount.line_id)
            .where(
                Conversation.id == conversation_id,
                ChannelAccount.channel_type == Conversation.channel_type
            )
        )
        result = await self.session.execute(stmt)
        log.info(f"get_channel_acc_by_conversation result {result}")
        return result.scalar_one_or_none()

    async def get_active_telegram_user_targets(self) -> list[tuple[str, str, str]]:
        stmt = (
            select(Conversation.id, ChannelAccount.phone, Conversation.client_phone)
            .join(ChannelAccount, and_(
                Conversation.line_id == ChannelAccount.line_id,
                Conversation.channel_type == ChannelAccount.channel_type
            ))
            .where(Conversation.channel_type == "telegram_user")
        )
        result = await self.session.execute(stmt)
        return result.all()