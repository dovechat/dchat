import uuid
from sqlalchemy import cast, desc, select, String, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from models.messages import Media, Message
from repo.base import BaseRepository

import logging
log = logging.getLogger("uvicorn.error")


class MessageRepository(BaseRepository[Message]):
    """Repository for message operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def get_media_ids_by_conversation(self, conversation_id: uuid.UUID) -> list[str]:
        from models.messages import Media
        media_list = await self.get_multi(
            filters={"conversation_id": conversation_id},
            join_model=Media,
            limit=10000,
        )
        return [str(m.media[0].id) for m in media_list if m.media]

    async def get_message_by_crm_message_id(self, conv_id: str, bx_message_id: str)-> Message | None:
        query = select(Message).where(
            Message.conversation_id == conv_id,
            cast(Message.raw_content["crm_message_id"], String) == bx_message_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class MediaRepository(BaseRepository[Media]):
    def __init__(self, session: AsyncSession):
        super().__init__(Media, session)

    async def get_by_message_id(self, message_id: int) -> list[Media]:
        return await self.get_multi(filters={"message_id": message_id})