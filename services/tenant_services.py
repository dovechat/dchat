import uuid

from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.auth_schemas import UserContext
from repo.tenant_repo import TenantRepository
from schemas.tenant_schemas import  (
    Tenant,
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

    async def get_all_tenants(self, current_user: UserContext) -> list[TenantResponse]:
        """List tenants where the current user is an active member."""
        log.info(f"----------- MONO TenantService.get_all_tenants current_user.id {current_user.id}  ")
        tenants = await self.repo.get_all_tenants(user_id=current_user.id)
        log.info(f"----------- MONO TenantService.get_all_tenants  {tenants}")
        return [TenantResponse.model_validate(t) for t in tenants]
