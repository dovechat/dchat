"""Admin repository for Green API instance pool."""
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repo.base import BaseRepository
from models.lines import Instance, InstancePoolEvent


class AdminInstanceRepository(BaseRepository[Instance]):
    """Репозиторий пула инстансов Green API."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Instance, session)

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[Instance]:
        filters: dict[str, Any] = {}
        if provider:
            filters["provider"] = provider
        if status:
            filters["status"] = status
        return await self.get_multi(skip=skip, limit=limit, filters=filters)

    async def get_instance(self, instance_id: UUID) -> Instance | None:
        return await self.get_by_id(instance_id)

    async def set_status(self, instance: Instance, new_status: str) -> Instance:
        return await self.update(instance, status=new_status)

    async def release(self, instance: Instance) -> Instance:
        """Освободить инстанс — убрать привязку к линии."""
        return await self.update(
            instance,
            status="idle",
            allocated_to_line_id=None,
        )

    async def create_instance(self, provider: str, external_id: str) -> Instance:
        return await self.create(
            provider=provider,
            external_id=external_id,
            status="idle",
        )

    async def count_by_status(self, status: str) -> int:
        return await self.count(filters={"status": status})


class AdminInstanceEventRepository(BaseRepository[InstancePoolEvent]):
    """Репозиторий событий пула инстансов."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InstancePoolEvent, session)

    async def log_event(
        self,
        instance_id: UUID,
        event_type: str,
        details: dict | None = None,
    ) -> InstancePoolEvent:
        return await self.create(
            instance_id=instance_id,
            event_type=event_type,
            details=details or {},
        )

    async def get_events_for_instance(
        self,
        instance_id: UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[InstancePoolEvent]:
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"instance_id": instance_id},
        )