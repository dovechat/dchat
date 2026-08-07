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

    async def get_conv_by_id(self, conv_id):
        return await self.get_by_id(conv_id)

    async def get_conversation_by_crm_id(
        self,
        line_id: uuid.UUID,
        channel_type: str,
        crm_chat_id: str
    ) -> Optional[Conversation]:
        """Find conversation by CRM identifiers"""
        return await self.get_one(
            line_id=line_id,
            channel_type=channel_type,
            crm_chat_id=crm_chat_id
        )

    async def create_conversation(
            self,
            line_id: uuid.UUID,
            channel_type: str,
            crm_chat_id: Optional[str] = None,
            client_phone: Optional[str] = None,
            meta: Optional[dict] = None
    ) -> Conversation:
        """Create new conversation"""
        return await self.create(
            line_id=line_id,
            channel_type=channel_type,
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

    async def get_conv_by_line_and_channel_type(
            self,
            line_id: uuid.UUID,
            channel_type: str,
            skip: int = 0,
            limit: int = 100
    ) -> List[Conversation]:
        """Get conversations for specific line anc channel_type"""
        res = await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"line_id": line_id, "channel_type": channel_type},
        )
        if res:
            return res[0]

    async def get_conversations_by_phone(
        self,
        line_id: uuid.UUID,
        client_phone: str,
        channel_type: str,
        skip: int = 0,
        limit: int = 1
    ) -> Conversation:
        """Get conversations for specific line"""
        log.info(f"ChatRepository.get_conversations_by_phone line_id {line_id} client_phone {client_phone} channel_type {channel_type}")
        res = await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"line_id": line_id, "client_phone": client_phone, "channel_type": channel_type}
        )
        log.info(f"ChatRepository.get_conversations_by_phone res {res}")
        if res and len(res) > 0:
            return res[0]

    # было: async def get_conversations_with_stats(self, tenant_id: uuid.UUID, skip: int, limit: int):
    async def get_conversations_with_stats(self, tenant_ids: list[uuid.UUID], skip: int, limit: int):
        stmt = (
            select(
                Conversation,
                Line.name.label("line_name"),
                Line.tenant_id.label("tenant_id"),
                func.count(Message.id).filter(Message.status == "sent").label("unread_count"),
                func.max(Message.created_at).label("last_message_at")
            )
            .join(Line, Conversation.line_id == Line.id)
            .outerjoin(Message, Conversation.id == Message.conversation_id)
            .where(Line.tenant_id.in_(tenant_ids))
            .group_by(Conversation.id, Line.name, Line.tenant_id)
            .order_by(desc(func.max(Message.created_at)))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_conversations_with_filters(
            self,
            tenant_ids: list[uuid.UUID],
            line_id: uuid.UUID | None = None,
            channel_type: str | None = None,
            is_closed: bool | None = None,
    ) -> list:
        stmt = (
            select(
                Conversation,
                Line.name.label("line_name"),
                Line.tenant_id.label("tenant_id"),
                func.count(Message.id).filter(Message.status == "sent").label("unread_count"),
                func.max(Message.created_at).label("last_message_at")
            )
            .join(Line, Conversation.line_id == Line.id)
            .outerjoin(Message, Conversation.id == Message.conversation_id)
            .where(Line.tenant_id.in_(tenant_ids))
            .group_by(Conversation.id, Line.name, Line.tenant_id)
            .order_by(desc(func.max(Message.created_at)))
        )
        if line_id is not None:
            stmt = stmt.where(Conversation.line_id == line_id)
        if channel_type is not None:
            stmt = stmt.where(Conversation.channel_type == channel_type)
        if is_closed is not None:
            stmt = stmt.where(Conversation.is_closed == is_closed)
        result = await self.session.execute(stmt)
        return result.all()


    async def get_conversation_with_messages(self, conversation_id: uuid.UUID):
        stmt = (
            select(Conversation)
            .join(Line, Conversation.line_id == Line.id)
            .where(
                and_(
                    Conversation.id == conversation_id
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


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


    async def get_channel_acc_by_line_id(
        self,
        line_id: uuid.UUID
    ) -> Optional[ChannelAccount]:
        """Get session_string from channel_account by conversation_id"""
        stmt = (
            select(ChannelAccount)
            .where(ChannelAccount.line_id == line_id)
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


    async def get_channel_acc_by_phone(
        self,
        phone: Optional[str] = None
    ) -> Optional[str]:
        """Get session_string from channel_account by conversation_id"""
        try:
            stmt = (
                select(ChannelAccount)
                .where(ChannelAccount.phone == phone)
                .order_by(ChannelAccount.updated_at.desc())  # свежие сверху
                .limit(1)
            ) 
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            log.error(f"get_channel_acc_by_phone {e}")

    async def get_line_phone_by_conversation(
            self,
            conversation_id: uuid.UUID,
    ) -> Optional[str]:
        try:
            stmt = (
                select(ChannelAccount.phone)
                .join(Conversation, Conversation.line_id == ChannelAccount.line_id)
                .where(
                    Conversation.id == conversation_id,
                    ChannelAccount.channel_type == Conversation.channel_type
                )
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            log.error(f"get_line_phone_by_conversation {e}")

    async def get_or_create_by_chat_id(
            self,
            line_id: uuid.UUID,
            chat_id: str,
            tenant_id: uuid.UUID,
            client_phone: str = None
    ) -> tuple[Conversation, bool]:
        stmt = select(Conversation).where(
            Conversation.line_id == line_id,
            Conversation.client_phone == chat_id
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if conversation:
            return conversation, False

        new_conv = Conversation(
            line_id=line_id,
            client_phone=chat_id,
            channel_type="telegram_bot",
            crm_chat_id=None,  # New chat should have this field empty
            meta={"username": client_phone} if client_phone else {}
        )
        self.session.add(new_conv)
        await self.session.commit()
        await self.session.refresh(new_conv)
        return new_conv, True

    async def get_lines_with_available_channels(self, tenant_id: uuid.UUID) -> list:
        stmt = (
            select(Line.id, Line.name, ChannelAccount.channel_type)
            .join(
                ChannelAccount,
                ChannelAccount.line_id == Line.id
            )
            .where(
                Line.tenant_id == tenant_id,
                Line.status == "active",
                ChannelAccount.channel_type != "telegram_bot",
                ~sa.exists().where(
                    and_(
                        Conversation.line_id == Line.id,
                        Conversation.channel_type == ChannelAccount.channel_type,
                    )
                )
            )
            .order_by(Line.name, ChannelAccount.channel_type)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def set_conversation_closed(self, conversation_id: uuid.UUID, is_closed: bool) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return None
        conv.is_closed = is_closed
        await self.session.flush()
        return conv

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