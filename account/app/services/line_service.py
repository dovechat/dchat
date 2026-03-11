import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.repositories.line_repo import (
    LineRepository,
    InstanceRepository,
    ChannelAccountRepository
)
from app.schemas.line_schemas import (
    LineCreate,
    LineUpdate,
    LineResponse,
    LineListResponse,
    SubscriptionPeriod
)
from schemas.auth_schemas import UserContext

import logging

log = logging.getLogger("uvicorn.error")


class LineService:

    def __init__(
            self,
            line_repo: LineRepository,
            instance_repo: InstanceRepository,
            channel_account_repo: ChannelAccountRepository
    ) -> None:
        self.line_repo = line_repo
        self.instance_repo = instance_repo
        self.channel_account_repo = channel_account_repo

    def _calculate_expiry(
            self,
            period: SubscriptionPeriod,
            is_demo: bool
    ) -> datetime:
        if is_demo:
            return datetime.now(timezone.utc) + timedelta(days=7)

        if period == SubscriptionPeriod.MONTH:
            return datetime.now(timezone.utc) + timedelta(days=30)
        else:
            return datetime.now(timezone.utc) + timedelta(days=365)

    async def _allocate_whatsapp_instance(
            self,
            line_id: uuid.UUID
    ) -> None:
        """
        Allocate WhatsApp instance from pool according to spec 5.2:
        - Search for free instance
        - Clean it before allocation
        - Bind to line and mark as busy
        - If no free instances - create new one
        """
        instance = await self.instance_repo.get_free_instance()

        if not instance:
            external_id = f"wa_instance_{uuid.uuid4().hex[:8]}"
            instance = await self.instance_repo.create_instance(
                provider="green_api",
                external_id=external_id
            )
            log.info(f"Created new WhatsApp instance: {external_id}")

        log.info(f"Allocating instance {instance.external_id} to line {line_id}")

        await self.instance_repo.allocate_instance(instance, line_id)

        await self.channel_account_repo.create_account(
            line_id=line_id,
            credentials_encrypted={"instance_id": instance.external_id},
            state_json={"qr_status": "pending"}
        )

    async def create_line(
            self,
            tenant_id: uuid.UUID,
            data: LineCreate,
    ) -> LineResponse:

        expires_at = self._calculate_expiry(data.subscription_period, data.is_demo)

        line = await self.line_repo.create_line(
            tenant_id=tenant_id,
            name=data.name,
            channel_type=data.channel_type.value,
            expires_at=expires_at,
            is_demo=data.is_demo
        )

        if data.channel_type.value == "whatsapp_green":
            await self._allocate_whatsapp_instance(line.id)

        return LineResponse.model_validate(line)

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

    async def update_line(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            data: LineUpdate,
    ) -> LineResponse:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        update_data = data.model_dump(exclude_unset=True)
        updated_line = await self.line_repo.update_line(line, **update_data)

        log.info(f"/n/n ******************** update_data {update_data}")
        log.info(f"/n/n ******************** updated_line {updated_line}")

        return LineResponse.model_validate(updated_line)

    async def delete_line(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
    ) -> None:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        if line.channel_type == "whatsapp_green":
            instance = await self.instance_repo.get_instance_by_line(line.id)
            if instance:
                await self.instance_repo.release_instance(instance)
                log.info(f"Released instance {instance.external_id} from line {line.id}")

        await self.line_repo.delete_line(line)