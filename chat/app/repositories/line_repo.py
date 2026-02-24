from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List
from models.lines import Line
from repo.base import BaseRepository

class LineRepository(BaseRepository[Line]):
    def __init__(self, session: AsyncSession):
        super().__init__(Line, session)

    async def get_by_ids(self, line_ids: List[UUID]) -> List[Line]:
        query = select(Line).where(Line.id.in_(line_ids))
        result = await self.session.execute(query)
        return list(result.scalars().all())