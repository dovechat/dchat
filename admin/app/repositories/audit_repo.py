"""Admin repository for audit log."""
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repo.base import BaseRepository
from models.tenants import AuditLog

import enum

def _serialize(obj):
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, enum.Enum):
        return obj.value
    return obj


class AdminAuditRepository(BaseRepository[AuditLog]):
    """Репозиторий журнала аудита."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditLog, session)

    async def log(
            self,
            actor_id: UUID,
            action: str,
            resource_type: str,
            resource_id: UUID | None = None,
            details: dict | None = None,
            tenant_id: UUID | None = None,
            old_state: dict | None = None,
            ip_address: str | None = None,
    ) -> AuditLog:
        return await self.create(
            user_id=actor_id,
            tenant_id=tenant_id,
            action=action,
            entity_type=resource_type,
            entity_id=str(resource_id) if resource_id else None,
            new_state=_serialize(details),
            old_state=_serialize(old_state),
            ip_address=ip_address,
        )

    async def get_logs(
            self,
            *,
            skip: int = 0,
            limit: int = 100,
            user_id: UUID | None = None,
            entity_type: str | None = None,
            action: str | None = None,
    ) -> list[AuditLog]:
        filters: dict[str, Any] = {}
        if user_id: filters["user_id"] = user_id
        if entity_type: filters["entity_type"] = entity_type
        if action: filters["action"] = action
        return await self.get_multi(skip=skip, limit=limit, filters=filters)