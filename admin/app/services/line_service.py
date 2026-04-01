"""Admin service: line management."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    ExtendLineRequest,
    LineListResponse,
    LineOut,
    MessageResponse,
    SetLineStatusRequest,
)

log = logging.getLogger("uvicorn.error")


class AdminLineService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def list_lines(
        self,
        skip: int,
        limit: int,
        tenant_id: UUID | None,
        channel_type: str | None,
        status: str | None,
        actor_id: UUID,
    ) -> LineListResponse:
        lines = await self._uow.lines.get_all_lines(
            skip=skip,
            limit=limit,
            tenant_id=tenant_id,
            channel_type=channel_type,
            status=status,
        )
        total = await self._uow.lines.count_lines(tenant_id=tenant_id, status=status)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="list_lines",
            resource_type="line",
            details={"filters": {"tenant_id": str(tenant_id) if tenant_id else None, "status": status}},
        )
        await self._uow.commit()

        return LineListResponse(
            items=[LineOut.model_validate(l) for l in lines],
            total=total,
        )

    async def get_line(self, line_id: UUID, actor_id: UUID) -> LineOut:
        line = await self._uow.lines.get_line(line_id)
        if not line:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")

        await self._uow.audit.log(
            actor_id=actor_id,
            action="get_line",
            resource_type="line",
            resource_id=line_id,
        )
        await self._uow.commit()
        return LineOut.model_validate(line)

    async def set_line_status(
        self,
        line_id: UUID,
        request: SetLineStatusRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        line = await self._uow.lines.get_line(line_id)
        if not line:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")

        old_status = line.status
        await self._uow.lines.set_line_status(line, request.status.value)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="set_line_status",
            resource_type="line",
            resource_id=line_id,
            details={"old_status": old_status, "new_status": request.status.value},
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: line {line_id} status {old_status} → {request.status.value}")
        return MessageResponse(message=f"Line status updated to {request.status.value}")

    async def extend_line(
        self,
        line_id: UUID,
        request: ExtendLineRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        line = await self._uow.lines.get_line(line_id)
        if not line:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")

        # Если срок уже истёк — продлеваем от текущего момента
        base = line.expires_at if line.expires_at and line.expires_at > datetime.now(timezone.utc) else datetime.now(timezone.utc)
        new_expires = base + timedelta(days=request.days)

        await self._uow.lines.extend_line(line, new_expires)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="extend_line",
            resource_type="line",
            resource_id=line_id,
            details={"days": request.days, "new_expires_at": new_expires.isoformat()},
        )
        await self._uow.commit()

        log.info(f"Admin {actor_id}: line {line_id} extended by {request.days}d, new expires {new_expires}")
        return MessageResponse(message=f"Line extended until {new_expires.date()}")