import uuid
from typing import List, Optional
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import ChannelAccount, Line
from models.messages import Conversation, Message
from repo.base import BaseRepository


class ChatRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)  # ← передать model и session

    async def get_conversation_by_crm_id(
        self,
        line_id: uuid.UUID,
        crm_type: str,
        crm_chat_id: str
    ) -> Optional[Conversation]:
        """Find conversation by CRM identifiers"""
        return await self.get_one(
            line_id=line_id,
            crm_type=crm_type,
            crm_chat_id=crm_chat_id
        )

    async def create_conversation(
            self,
            line_id: uuid.UUID,
            crm_type: str,
            crm_chat_id: str,
            client_phone: Optional[str] = None,
            meta: Optional[dict] = None
    ) -> Conversation:
        """Create new conversation"""
        return await self.create(
            line_id=line_id,
            crm_type=crm_type,
            crm_chat_id=crm_chat_id,
            client_phone=client_phone,
            meta=meta or {}
        )

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
    
    async def get_conversations_with_stats(self, tenant_id: uuid.UUID, skip: int, limit: int):
        stmt = (
            select(
                Conversation,
                func.count(Message.id).filter(Message.status == "sent").label("unread_count"),
                func.max(Message.created_at).label("last_message_at")
            )
            .join(Line, Conversation.line_id == Line.id)
            .outerjoin(Message, Conversation.id == Message.conversation_id)
            .where(Line.tenant_id == tenant_id)
            .group_by(Conversation.id)
            .order_by(desc(func.max(Message.created_at)))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.all()
    
    async def get_conversation_with_messages(self, conversation_id: uuid.UUID, tenant_id: uuid.UUID):
        stmt = (
            select(Conversation)
            .join(Line, Conversation.line_id == Line.id)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Line.tenant_id == tenant_id
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_by_conversation(
        self,
        conversation_id: uuid.UUID
    ) -> Optional[str]:
        """Get session_string from channel_account by conversation_id"""
        stmt = (
            select(ChannelAccount.session_string)
            .join(Conversation, Conversation.line_id == ChannelAccount.line_id)
            .where(Conversation.id == conversation_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def get_session_by_phone(
        self,
        phone: str
    ) -> Optional[str]:
        """Get session_string from channel_account by conversation_id"""
        stmt = (
            select(ChannelAccount.session_string)
            .where(ChannelAccount.phone == phone)
            .order_by(ChannelAccount.updated_at.desc())  # свежие сверху
            .limit(1)
        ) 
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def get_line_phone_by_conversation(
        self,
        conversation_id: uuid.UUID
    ) -> Optional[str]:
        """Get owner phone from channel_account by conversation_id"""
        stmt = (
            select(ChannelAccount.phone)
            .join(Conversation, Conversation.line_id == ChannelAccount.line_id)
            .where(Conversation.id == conversation_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()