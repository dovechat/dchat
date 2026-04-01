import uuid

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from models.lines import LineStatus
from repo.line_repo import LineRepository
from schemas.line_schemas import (
    LineResponse,
    LineListResponse,
)
from schemas.auth_schemas import UserContext

import logging
log = logging.getLogger("uvicorn.error")

class LineService:

    def __init__(
            self,
            line_repo: LineRepository,
    ) -> None:
        self.line_repo = line_repo

    async def get_lines(
            self,
            tenant_id: uuid.UUID,
    ) -> list[LineListResponse]:
        lines = await self.line_repo.get_lines_by_tenant(tenant_id)
        log.info(f"******** service lines tenant_id {tenant_id}")
        result = []
        for line in lines:
            days_until_expiry = None
            if line.expires_at:
                delta = line.expires_at - datetime.now(timezone.utc)
                days_until_expiry = max(0, delta.days)

            connection_status = "not_connected"
            if line.connection_state:
                connection_status = line.connection_state.get("status", "not_connected")

            line_dict = {
                **line.__dict__,
                "days_until_expiry": days_until_expiry,
                "connection_status": connection_status
            }
            result.append(LineListResponse.model_validate(line_dict))

        return result

    async def get_line(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
    ) -> LineResponse:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        return LineResponse.model_validate(line)

    async def expire_lines(self, now: datetime) -> dict:
        expired_lines = await self.line_repo.get_lines_to_expire(now)
        results = {"expired": 0, "expired_lines": [], "errors": 0}

        for line in expired_lines:
            try:
                await self.line_repo.update(line, status=LineStatus.expired)
                log.info(f"Line {line.id} (tenant {line.tenant_id}) expired")
                results["expired_lines"].append(line)
                results["expired"] += 1
            except Exception as e:
                log.error(f"Error expiring line {line.id}: {e}")
                results["errors"] += 1

        log.info(f"Expire run at {now}: {results}")
        return results

