from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from mono.models.instances import Instance, Provider, InstanceStatus
from .base import BaseRepository

class InstanceRepository(BaseRepository[Instance]):
    def __init__(self, session: AsyncSession):
        super().__init__(Instance, session)

    async def get_by_external_id(self, external_id: str) -> Instance | None:
        stmt = select(Instance).where(Instance.external_id == external_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
        """Update instance external_id by line_id"""
        instance = await self.session.execute(
            select(Instance).where(Instance.allocated_to_line_id == line_id)
        )
        instance = instance.scalar_one_or_none()
        log.info(f"+++++++++++ instance_repo.update_by_line instance {instance} ++++++++++++")
        if not instance:
            return None
    
        return await self.update(
            instance,
            external_id=external_id
        )