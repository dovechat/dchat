"""Admin API: Green API instance pool management."""
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    BulkCleanRequest,
    CreateInstanceRequest,
    InstanceListResponse,
    InstanceOut,
    MessageResponse,
)
from app.services.instance_service import AdminInstanceService

router = APIRouter(prefix="/instances", tags=["Admin — Instances"])


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    db: DBSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    provider: str | None = Query(None, description="green | waba"),
    status: str | None = Query(None, description="idle | allocated | busy | error"),
):
    """
    Список инстансов пула с агрегированными счётчиками по статусам.
    """
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.list_instances(
        skip=skip,
        limit=limit,
        provider=provider,
        status=status,
        actor_id=UUID(admin["sub"]),
    )


@router.get("/{instance_id}", response_model=InstanceOut)
async def get_instance(instance_id: UUID, db: DBSession, admin: AdminUser):
    """Детали инстанса."""
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.get_instance(instance_id, actor_id=UUID(admin["sub"]))


@router.post("", response_model=InstanceOut, status_code=201)
async def create_instance(
    request: CreateInstanceRequest,
    db: DBSession,
    admin: AdminUser,
):
    """Добавить новый инстанс в пул (ручное добавление)."""
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.create_instance(request, actor_id=UUID(admin["sub"]))


@router.post("/{instance_id}/clean", response_model=MessageResponse)
async def clean_instance(instance_id: UUID, db: DBSession, admin: AdminUser):
    """
    Принудительная очистка инстанса: снять привязку к линии,
    вернуть в пул свободных.
    """
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.clean_instance(instance_id, actor_id=UUID(admin["sub"]))


@router.post("/bulk-clean", response_model=MessageResponse)
async def bulk_clean_instances(
    request: BulkCleanRequest,
    db: DBSession,
    admin: AdminUser,
):
    """Массовая очистка группы инстансов."""
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.bulk_clean(request, actor_id=UUID(admin["sub"]))


@router.delete("/{instance_id}", response_model=MessageResponse)
async def delete_instance(instance_id: UUID, db: DBSession, admin: AdminUser):
    """
    Удалить инстанс из пула.
    Нельзя удалить allocated-инстанс — сначала нужно его очистить.
    """
    uow = AdminUnitOfWork(db)
    service = AdminInstanceService(uow)
    return await service.delete_instance(instance_id, actor_id=UUID(admin["sub"]))