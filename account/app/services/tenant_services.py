import uuid

from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.auth_schemas import UserContext
from app.core.uow import TenantMembershipUoW
from app.repositories.tenant_repo import RequisitsRepository, TenantRepository
from app.repositories.membership_repo import MembershipRepository
from app.schemas.tenant_schemas import  (
    BankDetailsRead,
    BankDetailsRUUpdate,
    MembershipCreate,
    Tenant,
    TenantCreate,
    TenantResponse,
)

import logging
log = logging.getLogger("uvicorn.error")


class TenantCreateService:
    def __init__(self, uow: TenantMembershipUoW):
        self.uow = uow

    async def create_with_owner(self, user_id: uuid.UUID, tenant_data: TenantCreate):
        async with self.uow:
            tenant = await self.uow.tenants.create_tenant(tenant_data)

            member_data = MembershipCreate(
                user_id=user_id,
                tenant_id=tenant.id,
                role="owner"
            )

            await self.uow.memberships.create_membership(member_data)

            return tenant


class TenantService:
    """Tenant service."""

    def __init__(
        self, repo: TenantRepository
    ) -> None:
        self.repo = repo

    async def create_tenant(
            self,
            user_id: uuid.UUID,
            data: TenantCreate,
    ) -> TenantResponse:
        """Create new tenant and link owner via membership"""
        tenant = await self.repo.create_tenant(data)

        member_repo = MembershipRepository()
        await member_repo.create(
            user_id=user_id,
            tenant_id=tenant.id,
            role="admin"
        )

        return TenantResponse.model_validate(tenant)

    async def get_all_tenants(self, current_user: UserContext) -> list[TenantResponse]:
        """List tenants where the current user is an active member."""
        log.info(f"----------- TenantService.get_all_tenants current_user.id {current_user.id}  ")
        tenants = await self.repo.get_all_tenants(user_id=current_user.id)
        log.info(f"----------- TenantService.get_all_tenants  {tenants}")
        return [TenantResponse.model_validate(t) for t in tenants]

    async def get_tenant(self, tenant_id: uuid.UUID, current_user: UserContext) -> TenantResponse:
        """Get tenant by ID and user ownership with context validation"""
        tenant = await self.repo.get_tenant_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")
        return TenantResponse.model_validate(tenant)

    async def update_tenant(self, tenant_id: uuid.UUID, data: dict, current_user: UserContext) -> TenantResponse:
        """Update tenant with ownership check in repo"""
        updated_tenant = await self.repo.update_tenant(
            tenant_id=tenant_id,
            data=data
        )
        if not updated_tenant:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")
        return TenantResponse.model_validate(updated_tenant)

    async def delete_tenant(self, tenant_id: uuid.UUID, current_user: UserContext) -> None:
        """Delete tenant with ownership check in repo"""
        success = await self.repo.delete_tenant(tenant_id=tenant_id)
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
    ) -> BankDetailsRead:
        result = await self.repo.update_bank_details(
            tenant_id=tenant_id, 
            data=data,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found or access denied")

        return BankDetailsRead.model_validate(result)