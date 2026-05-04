"""Admin service: line management."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    ChannelOut,
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
        name: str | None,
    ) -> LineListResponse:
        lines = await self._uow.lines.get_all_lines(
            skip=skip,
            limit=limit,
            tenant_id=tenant_id,
            channel_type=channel_type,
            status=status,
            name=name,
        )
        total = await self._uow.lines.count_lines(tenant_id=tenant_id, status=status, name=name)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="list_lines",
            resource_type="line",
            details={"filters": {"tenant_id": str(tenant_id) if tenant_id else None, "status": status}},
        )
        await self._uow.commit()

        items = []
        for l in lines:
            channels = await self._uow.channels.get_multi(filters={"line_id": l.id})
            items.append(LineOut(
                id=l.id,
                tenant_id=l.tenant_id,
                name=l.name,
                status=l.status,
                is_demo=l.is_demo,
                created_at=l.created_at,
                channels=[ChannelOut.model_validate(ch) for ch in channels],
            ))

        return LineListResponse(
            items=items,
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
        channels = await self._uow.channels.get_multi(filters={"line_id": line_id})
        return LineOut(
            id=line.id,
            tenant_id=line.tenant_id,
            name=line.name,
            status=line.status,
            is_demo=line.is_demo,
            created_at=line.created_at,
            channels=[ChannelOut.model_validate(ch) for ch in channels],
        )

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

        channels = await self._uow.channels.get_multi(filters={"line_id": line_id})
        max_expires = max(
            (ch.expires_at for ch in channels if ch.expires_at),
            default=None
        )
        base = max_expires if max_expires and max_expires > datetime.now(timezone.utc) else datetime.now(timezone.utc)
        new_expires = base + timedelta(days=request.days)

        await self._uow.lines.extend_line(line, new_expires)
        for ch in channels:
            await self._uow.channels.update(ch, expires_at=new_expires)

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