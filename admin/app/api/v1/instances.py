"""Admin API: Green API instance pool management."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    BulkCleanRequest,
    CreateInstanceRequest,
    InstanceListResponse,
    InstanceOut,
    MessageResponse,
    ReallocateRequest,
)
from app.services.instance_service import AdminInstanceService

router = APIRouter(prefix="/instances", tags=["Admin — Instances"])


def get_instance_service(db: DBSession) -> AdminInstanceService:
    return AdminInstanceService(AdminUnitOfWork(db))


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    provider: str | None = Query(None, description="green | waba"),
    status: str | None = Query(None, description="idle | allocated | busy | error"),
):
    return await service.list_instances(
        skip=skip, limit=limit, provider=provider, status=status,
        actor_id=UUID(admin["sub"]),
    )


@router.get("/{instance_id}", response_model=InstanceOut)
async def get_instance(
    instance_id: UUID,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.get_instance(instance_id, actor_id=UUID(admin["sub"]))


@router.post("", response_model=InstanceOut, status_code=201)
async def create_instance(
    request: CreateInstanceRequest,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.create_instance(request, actor_id=UUID(admin["sub"]))


@router.post("/{instance_id}/clean", response_model=MessageResponse)
async def clean_instance(
    instance_id: UUID,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.clean_instance(instance_id, actor_id=UUID(admin["sub"]))


@router.post("/bulk-clean", response_model=MessageResponse)
async def bulk_clean_instances(
    request: BulkCleanRequest,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.bulk_clean(request, actor_id=UUID(admin["sub"]))


@router.delete("/{instance_id}", response_model=MessageResponse)
async def delete_instance(
    instance_id: UUID,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.delete_instance(instance_id, actor_id=UUID(admin["sub"]))


@router.post("/{instance_id}/reallocate", response_model=MessageResponse)
async def reallocate_instance(
    instance_id: UUID,
    request: ReallocateRequest,
    admin: AdminUser,
    service: AdminInstanceService = Depends(get_instance_service),
):
    return await service.reallocate_instance(instance_id, request.line_id, actor_id=UUID(admin["sub"]))