import uuid
from sqlalchemy import select
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
        result = await self.session.execute(
            select(Message.media_id)
            .where(Message.conversation_id == conversation_id)
            .where(Message.media_id.isnot(None))
            .where(Message.media_id != "None")
        )
        return list(result.scalars().all())


class MediaRepository(BaseRepository[Media]):
    def __init__(self, session: AsyncSession):
        super().__init__(Media, session)

    async def get_by_message_id(self, message_id: int) -> list[Media]:
        return await self.get_multi(filters={"message_id": message_id})