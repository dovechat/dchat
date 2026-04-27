import json
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.lines import ChannelAccount, Line, Instance, InstanceStatus, Provider
from repo.base import BaseRepository
import logging

log = logging.getLogger("uvicorn.error")


class LineRepository(BaseRepository[Line]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Line, session)

    async def create_line(
            self,
            tenant_id: uuid.UUID,
            name: str,
            is_demo: bool = False,
    ) -> Line:
        return await self.create(
            tenant_id=tenant_id,
            name=name,
            is_demo=is_demo,
            connection_state={"status": "not_connected"}
        )

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

    async def update_line(
            self,
            line: Line,
            **data
    ) -> Line:
        return await self.update(line, **data)

    async def delete_line(
            self,
            line: Line
    ) -> None:
        await self.delete(line)

    async def update_connection_state(self, line_id: uuid.UUID, state: dict) -> None:
        line = await self.get_by_id(line_id)
        if line:
            await self.update(line, connection_state=state)

    async def get_lines_with_expires(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[tuple[Line, datetime | None, list[str]]]:
        query = (
            select(
                Line,
                func.max(ChannelAccount.expires_at).label("max_expires_at"),
                func.array_agg(ChannelAccount.channel_type).label("channel_types")
            )
            .outerjoin(ChannelAccount, ChannelAccount.line_id == Line.id)
            .where(Line.tenant_id == tenant_id)
            .group_by(Line.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.all()

