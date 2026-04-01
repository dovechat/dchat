"""Admin API: lines management."""
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    ExtendLineRequest,
    LineListResponse,
    LineOut,
    MessageResponse,
    SetLineStatusRequest,
)
from app.services.line_service import AdminLineService

router = APIRouter(prefix="/lines", tags=["Admin — Lines"])


@router.get("", response_model=LineListResponse)
async def list_lines(
    db: DBSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: UUID | None = Query(None),
    channel_type: str | None = Query(None),
    status: str | None = Query(None),
):
    """Список всех линий по всем тенантам с фильтрацией."""
    uow = AdminUnitOfWork(db)
    service = AdminLineService(uow)
    return await service.list_lines(
        skip=skip,
        limit=limit,
        tenant_id=tenant_id,
        channel_type=channel_type,
        status=status,
        actor_id=UUID(admin["sub"]),
    )


@router.get("/{line_id}", response_model=LineOut)
async def get_line(line_id: UUID, db: DBSession, admin: AdminUser):
    """Детали линии."""
    uow = AdminUnitOfWork(db)
    service = AdminLineService(uow)
    return await service.get_line(line_id, actor_id=UUID(admin["sub"]))


@router.patch("/{line_id}/status", response_model=MessageResponse)
async def set_line_status(
    line_id: UUID,
    request: SetLineStatusRequest,
    db: DBSession,
    admin: AdminUser,
):
    """
    Изменить статус линии.
    Используется для принудительной блокировки, разблокировки и т.д.
    """
    uow = AdminUnitOfWork(db)
    service = AdminLineService(uow)
    return await service.set_line_status(line_id, request, actor_id=UUID(admin["sub"]))


@router.post("/{line_id}/extend", response_model=MessageResponse)
async def extend_line(
    line_id: UUID,
    request: ExtendLineRequest,
    db: DBSession,
    admin: AdminUser,
):
    """Продлить срок действия линии на указанное количество дней."""
    uow = AdminUnitOfWork(db)
    service = AdminLineService(uow)
    return await service.extend_line(line_id, request, actor_id=UUID(admin["sub"]))