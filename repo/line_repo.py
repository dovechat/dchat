import json
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import ChannelAccount, Line
from repo.base import BaseRepository
import logging

log = logging.getLogger("uvicorn.error")


class LineRepository(BaseRepository[Line]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Line, session)

    async def get_lines_by_tenant(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[Line]:
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"tenant_id": tenant_id}
        )

    async def get_line_by_id(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID
    ) -> Line | None:
        return await self.get_by_id(line_id, tenant_id=tenant_id)


class ChannelAccountRepository(BaseRepository[ChannelAccount]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChannelAccount, session)

    async def get_by_line(
            self,
            line_id: uuid.UUID
    ) -> ChannelAccount | None:
        existing = await self.get_multi(
            filters={"line_id": line_id},
            limit=1
        )
        return existing[0] if existing else None

    async def update_connection_status(self, line_id: uuid.UUID, status: str) -> None:
        account = await self.get_by_line(line_id)
        if account:
            await self.update(
                account,
                connection_status=status,
                last_checked_at=datetime.now()
            )