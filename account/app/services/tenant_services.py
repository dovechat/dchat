import uuid

from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant_repo import RequisitsRepository, TenantRepository
from app.schemas.tenant_schemas import  (
    BankDetailsRead,
    BankDetailsRUUpdate,
    Tenant,
    TenantCreate,
    TenantResponse,
)

import logging
log = logging.getLogger("uvicorn.error")

class TenantService:
    """Tenant service."""

    def __init__(
        self, repo: TenantRepository
    ) -> None:
        self.repo = repo

    async def create_tenant(
        self,
        user_id: uuid.UUID,
        data: Tenant,
    ) -> TenantResponse:
        """Create new tenant"""

        insert_data = TenantCreate(
            **data.model_dump(),
            user_id=user_id,
        )
        
        tenant = await self.repo.create_tenant(insert_data)
        return TenantResponse.model_validate(tenant)


    async def get_all_tenants(self, user_id: uuid.UUID) -> list[TenantResponse]:
        """List tenants for specific user"""
        tenants = await self.repo.get_all_tenants(user_id=user_id)
        return [TenantResponse.model_validate(t) for t in tenants]

    async def get_tenant(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> TenantResponse:
        """Get tenant by ID and user ownership"""
        tenant = await self.repo.get_tenant_by_id(tenant_id, user_id=user_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")
        return TenantResponse.model_validate(tenant)

    async def update_tenant(self, tenant_id: uuid.UUID, data: dict, user_id: uuid.UUID) -> TenantResponse:
        """Update tenant with ownership check in repo"""
        updated_tenant = await self.repo.update_tenant(
            tenant_id=tenant_id,
            user_id=user_id,
            data=data
        )
        if not updated_tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")
        return TenantResponse.model_validate(updated_tenant)

    async def delete_tenant(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete tenant with ownership check in repo"""
        success = await self.repo.delete_tenant(tenant_id=tenant_id, user_id=user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")


class RequisitsService():
    def __init__(
        self, repo: RequisitsRepository
    ) -> None:
        self.repo = repo

    async def update_tenant_banking(
            self,
            tenant_id: uuid.UUID,
            data: BankDetailsRUUpdate,
            user_id: uuid.UUID,
    ) -> BankDetailsRead:
        result = await self.repo.update_bank_details(
            tenant_id=tenant_id, 
            data=data,
            user_id=user_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")

        return BankDetailsRead.model_validate(result)