import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from models.lines import Line, ChannelAccount, Instance
from repo.base import BaseRepository

import logging
log = logging.getLogger(__name__)

class LineRepository(BaseRepository[Line]):
    def __init__(self, session: AsyncSession):
        super().__init__(Line, session)

    async def get_by_ids(self, line_ids: List[uuid.UUID]) -> List[Line]:
        query = select(Line).where(Line.id.in_(line_ids))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def set_line_status(self, line_id: str, state: dict):
        """Update status to active using base update logic"""
        line = await self.get_by_id(line_id)
        if line:
            res = await self.update(line, connection_state=state)
            return res


class InstanceRepository(BaseRepository[Instance]):
    def __init__(self, session: AsyncSession):
        super().__init__(Line, session)

    async def get_line_by_instance_id(self, instance_id: str) -> Line | None:
        query = select(Line).join(
            Instance,
            Instance.allocated_to_line_id == Line.id,
            isouter=False  # INNER JOIN
        ).where(Instance.external_id == instance_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()