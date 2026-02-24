from uuid import UUID
from typing import List, Optional
from sqlalchemy import select
from models.tenants import ResourcePermission
from repo.base import BaseRepository

class PermissionRepository(BaseRepository[ResourcePermission]):
    def __init__(self, session):
        super().__init__(ResourcePermission, session)

    async def get_by_user_and_resource(
        self, 
        user_id: UUID, 
        resource_type: str, 
        resource_id: UUID
    ) -> Optional[ResourcePermission]:
        query = select(ResourcePermission).where(
            ResourcePermission.user_id == user_id,
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_user_and_resource_type(self, user_id: UUID, resource_type: str) -> List[ResourcePermission]:
        query = select(ResourcePermission).where(
            ResourcePermission.user_id == user_id,
            ResourcePermission.resource_type == resource_type
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())