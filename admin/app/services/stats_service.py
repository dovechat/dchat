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
        blocked_users = await self._uow.users.count_users(status="suspended")

        total_lines = await self._uow.lines.count_lines()
        active_lines = await self._uow.lines.count_lines(status="active")
        blocked_lines = await self._uow.lines.count_lines(status="disabled")
        expired_lines = await self._uow.lines.count_lines(status="expired")

        total_instances = await self._uow.instances.count(filters={})
        idle_instances = await self._uow.instances.count_by_status("idle")
        allocated_instances = await self._uow.instances.count_by_status("allocated")
        error_instances = await self._uow.instances.count_by_status("error")

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

    async def _resolve_entity_name(self, entity_type: str | None, entity_id: str | None) -> str | None:
        if not entity_type or not entity_id:
            return None
        if entity_type == "line":
            obj = await self._uow.lines.get_by_id(entity_id)
            return obj.name if obj else "удалено"
        if entity_type == "tenant":
            obj = await self._uow.tenants.get_by_id(entity_id)
            return obj.name if obj else "удалено"
        if entity_type == "instance":
            obj = await self._uow.instances.get_by_id(entity_id)
            return obj.external_id if obj else "удалено"
        if entity_type == "user":
            obj = await self._uow.users.get_user(entity_id)
            return obj.email if obj else "удалено"


    async def get_logs(
            self,
            skip: int,
            limit: int,
            user_id_filter: UUID | None,
            entity_type: str | None,
            action: str | None,
            requesting_user_id: UUID,
    ) -> AuditLogListResponse:
        logs = await self._uow.audit.get_logs(
            skip=skip,
            limit=limit,
            user_id=user_id_filter,
            entity_type=entity_type,
            action=action,
        )
        items = []
        for entry in logs:
            user_obj = await self._uow.users.get_user(entry.user_id) if entry.user_id else None
            entity_name = await self._resolve_entity_name(entry.entity_type, entry.entity_id)
            items.append(AuditLogOut.model_validate(entry).model_copy(update={
                "user": user_obj.email if user_obj else None,
                "entity_name": entity_name,
            }))
        return AuditLogListResponse(items=items, total=len(logs))