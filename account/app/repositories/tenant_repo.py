"""Repository for working with tasks"""
import uuid

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenants import BankDetails, Tenant
from app.schemas.tenant_schemas import BankDetailsRUUpdate, TenantCreate, Tenant as TenandPD
from repo.base import BaseRepository


import logging
log = logging.getLogger("uvicorn.error")

class TenantRepository(BaseRepository[Tenant]):
    """Repository for working with tenants"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tenant, session)

    async def create_tenant(
        self,
        data: TenantCreate,
    ) -> Tenant:
        """Create new tenant"""
        return await self.create(
            **data.model_dump()
        )

    async def get_all_tenants(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> list[Tenant]:
        """Get all tenants for user"""
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"user_id": user_id}
        )

    async def get_tenant_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Tenant | None:
        """Get tenant by ID and owner"""
        return await self.get_by_id(tenant_id, user_id=user_id)

    async def update_tenant(self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: dict) -> Tenant | None:
        """Update tenant only if owned by user"""
        # Search with ownership check
        tenant = await self.get_by_id(tenant_id, user_id=user_id)
        if not tenant:
            return None

        return await self.update(
            tenant,
            **data
        )

    async def delete_tenant(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete tenant using BaseRepository logic"""
        tenant = await self.get_tenant_by_id(tenant_id, user_id)
        if not tenant:
            return False
        await self.delete(tenant)
        return True


class RequisitsRepository(BaseRepository[BankDetails]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(BankDetails, session)

    async def update_bank_details(
            self,
            tenant_id: uuid.UUID,
            data: BankDetailsRUUpdate,
            user_id: uuid.UUID
    ) -> BankDetails:
        # Use get_multi to find record by tenant_id instead of primary key
        existing_records = await self.get_multi(
            filters={"tenant_id": tenant_id},
            limit=1
        )
        requisites = existing_records[0] if existing_records else None

        # Handle data conversion and strip user_id to prevent TypeError
        update_data = data.model_dump() if hasattr(data, "model_dump") else data
        update_data.pop("user_id", None)

        if requisites:
            return await self.update(requisites, **update_data)

        # Create new entry specifically linked to the tenant
        return await self.create(
            **update_data,
            tenant_id=tenant_id
        )
