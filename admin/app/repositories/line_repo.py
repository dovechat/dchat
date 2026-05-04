"""Admin repository for lines."""
from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repo.base import BaseRepository
from models.lines import Line, ChannelAccount


class AdminLineRepository(BaseRepository[Line]):
    """Репозиторий линий для нужд админки."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Line, session)

    async def get_all_lines(
            self,
            *,
            skip: int = 0,
            limit: int = 100,
            tenant_id: UUID | None = None,
            channel_type: str | None = None,
            status: str | None = None,
            name: str | None = None,
    ) -> list[Line]:
        filters: dict[str, Any] = {}
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if channel_type:
            filters["channel_type"] = channel_type
        if status:
            filters["status"] = status
        if name:
            filters["name"] = f'%{name}%'
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters=filters,
            join_model=ChannelAccount if channel_type else None,
        )

    async def get_line(self, line_id: UUID) -> Line | None:
        return await self.get_by_id(line_id)

    async def set_line_status(self, line: Line, new_status: str) -> Line:
        return await self.update(line, status=new_status)

    async def extend_line(self, line: Line, new_expires_at: datetime) -> Line:
        return await self.update(line, status="active")

    async def count_lines(
            self,
            tenant_id: UUID | None = None,
            status: str | None = None,
            name: str | None = None,
    ) -> int:
        filters: dict[str, Any] = {}
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status:
            filters["status"] = status
        if name:
            filters["name"] = f'%{name}%'
        return await self.count(filters=filters)


class AdminChannelAccountRepository(BaseRepository[ChannelAccount]):
    """Репозиторий channel_accounts для нужд админки."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChannelAccount, session)

    async def get_by_line(self, line_id: UUID) -> ChannelAccount | None:
        return await self.get_by_id(line_id, line_id=line_id)

    async def set_connection_status(
        self, account: ChannelAccount, status: str, error: str | None = None
    ) -> ChannelAccount:
        kwargs: dict[str, Any] = {"connection_status": status}
        if error is not None:
            kwargs["connection_error"] = error
        return await self.update(account, **kwargs)