from uuid import UUID
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.line_repo import LineRepository
from app.repositories.permission_repo import PermissionRepository

import logging
log = logging.getLogger(__name__)

class LineService:
    def __init__(self, db: AsyncSession):
        self.permission_repo = PermissionRepository(db)
        self.line_repo = LineRepository(db)

    async def get_user_lines(self, user_id: UUID, role: str, tenant_id: UUID) -> List:
        if role == "owner":
            log.info(f"******** Owner {user_id}, getting all lines for tenant {tenant_id}")
            return await self.line_repo.get_multi(filters={"tenant_id": tenant_id})
        else:
            line_ids = await self.permission_repo.get_user_line_ids(user_id)
            log.info(f"******** Member {user_id}, line_ids {line_ids}")
            if not line_ids:
                return []
            return await self.line_repo.get_multi(filters={"id": line_ids})