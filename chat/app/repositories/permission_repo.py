# app/repositories/permission_repo.py
from uuid import UUID
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenants import ResourcePermission
from repo.base import BaseRepository

class PermissionRepository(BaseRepository[ResourcePermission]):
    def __init__(self, session: AsyncSession):
        super().__init__(ResourcePermission, session)

    async def get_user_line_ids(self, user_id: UUID) -> List[UUID]:
        filters = {
            "user_id": user_id,
            "resource_type": "line"
        }
        perms = await self.get_multi(filters=filters)
        return [p.resource_id for p in perms]