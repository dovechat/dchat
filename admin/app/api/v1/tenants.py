"""Admin API: tenants management."""
import uuid

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import AdminUser
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    TenantListResponse,
    TenantOut,
    SetTenantStatusRequest,
    MessageResponse,
)
from app.services.tenant_service import AdminTenantService
from core.dependencies import get_db

router = APIRouter(prefix="/tenants", tags=["Admin — Tenants"])


def get_service(session=Depends(get_db)) -> AdminTenantService:
    return AdminTenantService(AdminUnitOfWork(session))


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    admin: AdminUser,
    svc: AdminTenantService = Depends(get_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    name: str | None = Query(None),
    status: str | None = Query(None),
):
    return await svc.list_tenants(
        skip=skip, limit=limit, name=name, status=status,
        actor_id=uuid.UUID(admin["sub"]),
    )


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: uuid.UUID,
    admin: AdminUser,
    svc: AdminTenantService = Depends(get_service),
):
    return await svc.get_tenant(tenant_id, actor_id=uuid.UUID(admin["sub"]))


@router.patch("/{tenant_id}/status", response_model=MessageResponse)
async def set_tenant_status(
    tenant_id: uuid.UUID,
    body: SetTenantStatusRequest,
    admin: AdminUser,
    svc: AdminTenantService = Depends(get_service),
):
    return await svc.set_tenant_status(tenant_id, body, actor_id=uuid.UUID(admin["sub"]))