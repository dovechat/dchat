import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.lines import Instance, InstanceStatus, Line, Provider
from repo.base import BaseRepository

import logging
log = logging.getLogger("uvicorn.error")


class InstanceRepository(BaseRepository[Instance]):
    def __init__(self, session: AsyncSession):
        super().__init__(Instance, session)

    async def release_instance(
            self,
            instance: Instance
    ) -> Instance:
        return await self.update(
            instance,
            status=InstanceStatus.idle,
            allocated_to_line_id=None,
            last_cleanup_at=datetime.utcnow()
        )

    async def get_instance_by_line(self, line_id: uuid.UUID) -> Instance | None:
        result = await self.get_multi(filters={"allocated_to_line_id": line_id})
        return result[0] if result else None

    async def get_by_external_id(self, external_id: str) -> Instance | None:
        result = await self.get_multi(filters={"external_id": external_id})
        return result[0] if result else None

    async def get_or_create_by_external_id(self, provider: Provider, external_id: str) -> Instance:
        instance = await self.get_by_external_id(external_id)
        if not instance:
            instance = Instance(
                provider=provider,
                external_id=external_id,
                status=InstanceStatus.idle
            )
            self.session.add(instance)
            await self.session.flush()
        return instance

    async def update_by_line(self, line_id: uuid.UUID, external_id: str) -> Instance | None:
        instance = await self.get_instance_by_line(line_id)
        if not instance:
            return None
        return await self.update(instance, external_id=external_id)

    async def get_free_instance(self, provider: Provider = Provider.green) -> Instance | None:
        query = select(Instance).where(
            Instance.provider == provider,
            Instance.status == InstanceStatus.idle,
            Instance.allocated_to_line_id.is_(None)
        ).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_line_by_instance_id(self, instance_id: str) -> Line | None:
        query = select(Line).join(
            Instance,
            Instance.allocated_to_line_id == Line.id,
            isouter=False  # INNER JOIN
        ).where(Instance.external_id == instance_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_free_green_instance(self) -> Instance:
        log.info("repo.instance_repo get_free_green_instance")
        row = await self.get_multi(
            limit=1,
            filters={"status": "idle"}
        )
        log.info(f"repo.instance_repo get_free_green_instance row {row}")
        return row[0] if row else None

    async def allocate_instance(self, instance: Instance, line_id: uuid.UUID) -> None:
        instance.allocated_to_line_id = line_id
        instance.status = InstanceStatus.busy
        await self.update(instance)