from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from core.dependencies import get_db, get_current_user
from core.dependencies import get_tenant_repo
from schemas.tenant_schemas import Tenant, TenantResponse
from services.tenant_services import TenantService
from schemas.auth_schemas import UserContext

import logging
log = logging.getLogger("uvicorn.error")

auth_scheme = HTTPBearer()

tenant_router = APIRouter(tags=["Tenant"], prefix="/tenant", dependencies=[Depends(auth_scheme)])


def get_tenant_service(
    tenant_repo=Depends(get_tenant_repo),
) -> TenantService:
    return TenantService(tenant_repo)


@tenant_router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    current_user: UserContext = Depends(get_current_user),
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Get all tenants"""
    return await tenant_service.get_all_tenants(current_user=current_user)