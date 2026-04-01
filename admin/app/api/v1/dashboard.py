"""Admin API: audit log and dashboard stats."""
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdminStatsOut,
    AuditLogListResponse,
)
from app.services.stats_service import AdminAuditService, AdminStatsService

router = APIRouter(tags=["Admin — Dashboard"])


@router.get("/stats", response_model=AdminStatsOut)
async def get_stats(db: DBSession, admin: AdminUser):
    """
    Сводная статистика для дашборда:
    пользователи, линии, инстансы — по статусам.
    """
    uow = AdminUnitOfWork(db)
    service = AdminStatsService(uow)
    return await service.get_stats(actor_id=UUID(admin["sub"]))


@router.get("/audit", response_model=AuditLogListResponse)
async def get_audit_log(
    db: DBSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: UUID | None = Query(None, description="Фильтр по исполнителю"),
    entity_type: str | None = Query(None, description="user | line | instance | billing | admin"),
    action: str | None = Query(None, description="Конкретное действие"),
):
    """
    Журнал аудита административных действий.
    Фиксирует все ключевые операции: изменения статусов, сброс паролей,
    корректировки баланса, операции с инстансами.
    """
    uow = AdminUnitOfWork(db)
    service = AdminAuditService(uow)
    return await service.get_logs(
        skip=skip,
        limit=limit,
        user_id_filter=user_id,
        entity_type=entity_type,
        action=action,
        requesting_user_id=UUID(admin["sub"]),
    )