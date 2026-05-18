import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm

from core.dependencies import get_db, get_current_user
from app.core.dependencies import (
    get_requisits_repo, check_tenant_access,
    get_tenant_repo, get_tenant_uow
)
from app.schemas.tenant_schemas import (
    BankDetailsRead, BankDetailsRUUpdate,
    Tenant, TenantResponse,
)
from app.services.tenant_services import RequisitsService, TenantCreateService, TenantService
from schemas.auth_schemas import UserContext
from services.auth_service import AuthService

import logging
log = logging.getLogger("uvicorn.error")

auth_scheme = HTTPBearer()

tenant_router = APIRouter(tags=["Tenant"], prefix="/tenant", dependencies=[Depends(auth_scheme)])


def get_tenant_service(
    tenant_repo=Depends(get_tenant_repo),
) -> TenantService:
    return TenantService(tenant_repo)

def get_tenant_uow_service(
    tenant_uow=Depends(get_tenant_uow),
) -> TenantCreateService:
    return TenantCreateService(tenant_uow)

def get_requisits_service(
        requisits_repo=Depends(get_requisits_repo),
) -> RequisitsService:
    return RequisitsService(requisits_repo)


@tenant_router.post("/create", response_model=TenantResponse, status_code=201)
async def create_tenant_rt(
        data: Tenant,
        current_user: UserContext = Depends(get_current_user),
        tenant_create_service: TenantCreateService = Depends(get_tenant_uow_service)
) -> TenantResponse:
    """Create tenant"""
    result = await tenant_create_service.create_with_owner(current_user.id, data)
    return result


@tenant_router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Get tenant by ID"""
    return await tenant_service.get_tenant(tenant_id=tenant_id, current_user=current_user)

@tenant_router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    current_user: UserContext = Depends(get_current_user),
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Get all tenants"""
    return await tenant_service.get_all_tenants(current_user=current_user)

@tenant_router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    data: Tenant,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    tenant_service: TenantService = Depends(get_tenant_service)
) -> Tenant:
    """Update tenant details"""
    return await tenant_service.update_tenant(
        tenant_id=tenant_id, 
        data=data.model_dump(),
        current_user=current_user
    )

@tenant_router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Delete tenant"""
    await tenant_service.delete_tenant(tenant_id=tenant_id, current_user=current_user)


@tenant_router.patch("/{tenant_id}/banking/ru", response_model=BankDetailsRead)
async def update_banking(
    data: BankDetailsRUUpdate,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    requisits_service: RequisitsService = Depends(get_requisits_service)
):
    return await requisits_service.update_tenant_banking(tenant_id, data.model_dump(exclude_unset=True))
