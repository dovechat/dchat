"""Admin service: stats dashboard and audit log."""
import logging
from uuid import UUID

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdminStatsOut,
    AuditLogListResponse,
    AuditLogOut,
)

log = logging.getLogger("uvicorn.error")


class AdminStatsService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def get_stats(self, actor_id: UUID) -> AdminStatsOut:
        total_users = await self._uow.users.count_users()
        active_users = await self._uow.users.count_users(status="active")
        blocked_users = await self._uow.users.count_users(status="blocked")

        total_lines = await self._uow.lines.count_lines()
        active_lines = await self._uow.lines.count_lines(status="active")
        blocked_lines = await self._uow.lines.count_lines(status="blocked")
        expired_lines = await self._uow.lines.count_lines(status="expired")

        total_instances = await self._uow.instances.count(filters={})
        idle_instances = await self._uow.instances.count_by_status("idle")
        allocated_instances = await self._uow.instances.count_by_status("allocated")
        error_instances = await self._uow.instances.count_by_status("error")

        await self._uow.audit.log(
            actor_id=actor_id,
            action="view_stats",
            resource_type="admin",
        )
        await self._uow.commit()

        return AdminStatsOut(
            total_users=total_users,
            active_users=active_users,
            blocked_users=blocked_users,
            total_lines=total_lines,
            active_lines=active_lines,
            blocked_lines=blocked_lines,
            expired_lines=expired_lines,
            total_instances=total_instances,
            idle_instances=idle_instances,
            allocated_instances=allocated_instances,
            error_instances=error_instances,
        )


class AdminAuditService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def get_logs(
        self,
        skip: int,
        limit: int,
        actor_id_filter: UUID | None,
        resource_type: str | None,
        action: str | None,
        requesting_actor_id: UUID,
    ) -> AuditLogListResponse:
        logs = await self._uow.audit.get_logs(
            skip=skip,
            limit=limit,
            actor_id=actor_id_filter,
            resource_type=resource_type,
            action=action,
        )
        total = len(logs)

        # Само это действие тоже логируем — но без рекурсии, минимально
        log.debug(f"Admin {requesting_actor_id} viewed audit log (skip={skip}, limit={limit})")

        return AuditLogListResponse(
            items=[AuditLogOut.model_validate(entry) for entry in logs],
            total=total,
        )