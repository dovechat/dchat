"""Repository for working with tasks"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenants import Membership, Tenant
from repo.base import BaseRepository

import logging
log = logging.getLogger("uvicorn.error")

class TenantRepository(BaseRepository[Tenant]):
    """Repository for working with tenants"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tenant, session)

    async def get_all_tenants(
            self,
            user_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[Tenant]:
        """Get all tenants for user via Membership association."""
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"user_id": user_id, "is_active": True},
            join_model=Membership
        )

