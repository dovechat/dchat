import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from models.messages import Conversation
from repo.base import BaseRepository

import logging
log = logging.getLogger(__name__)

class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)  # ← передать model и session

    async def get_by_line(
        self,
        line_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        crm_type: str | None = None,
    ) -> List[Conversation]:
        """Get conversations for specific line"""
        filters = {"line_id": line_id}
        if crm_type is not None:
            filters["crm_type"] = crm_type
        return await self.get_multi(skip=skip, limit=limit, filters=filters)