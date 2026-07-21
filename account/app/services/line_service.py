import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.repositories.line_repo import LineRepository
from repo.instance_repo import InstanceRepository
from models.billing import LedgerOperationType 
from repo.billing_repo import BalanceLedgerRepository, BalanceRepository
from repo.line_repo import ChannelAccountRepository
from repo.user import UserRepository
from app.schemas.channel_schemas import ChannelAccountResponse
from schemas.line_schemas import  ChannelType
from app.schemas.line_schemas import (
    ChannelCreate,
    ChannelRenew,
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
            billing_repo: BalanceRepository,
            ledger_repo: BalanceLedgerRepository,
            line_repo: LineRepository,
            instance_repo: InstanceRepository,
            channel_account_repo: ChannelAccountRepository,
            user_repo: UserRepository
    ) -> None:
        self.billing_repo = billing_repo
        self.ledger_repo = ledger_repo
        self.line_repo = line_repo
        self.instance_repo = instance_repo
        self.channel_account_repo = channel_account_repo
        self.user_repo = user_repo

    def _calculate_expiry(
            self,
            period: SubscriptionPeriod,
            is_demo: bool,
            user_created_at: datetime,
    ) -> datetime:
        if is_demo:
            return user_created_at + timedelta(days=2)
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
            return "No free instances, it needs to buy new one"
            # raise HTTPException(status_code=400, detail="No free instances, it needs to buy new one")
            '''
            external_id = f"wa_instance_{uuid.uuid4().hex[:8]}"
            instance = await self.instance_repo.create_instance(
                provider="green",
                external_id=external_id
            )
            log.info(f"Created new WhatsApp instance: {external_id}")
            '''

        log.info(f"Allocating instance {instance.external_id} to line {line_id}")

        await self.instance_repo.allocate_instance(instance, line_id)

        account = await self.channel_account_repo.get_by_line_and_type(line_id, ChannelType.WHATSAPP_GREEN)
        if account:
            await self.channel_account_repo.update_account(
                account,
                credentials_encrypted={"instance_id": instance.external_id},
                state_json={"qr_status": "pending"}
            )
        else:
            await self.channel_account_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.WHATSAPP_GREEN,
                credentials_encrypted={"instance_id": instance.external_id},
                state_json={"qr_status": "pending"}
            )

    async def add_channel(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            data: ChannelCreate,
            user: UserContext,
    ) -> ChannelAccountResponse:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        log.info(f"\n\n LineService.add_channel line {line}")
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        existing = await self.channel_account_repo.get_by_line_and_type(line_id, data.channel_type)
        log.info(f"\n\n LineService.add_channel existing {existing}")
        if existing:
            raise HTTPException(status_code=400, detail="Channel already exists for this provider")

        user_db = await self.user_repo.get_by_id(user.id)
        user_created_at = user_db.created_at.replace(tzinfo=timezone.utc)
        is_demo = datetime.now(timezone.utc) < user_created_at + timedelta(days=2)
        expires_at = self._calculate_expiry(
            data.subscription_period, is_demo, user_db.created_at
        )

        account = await self.channel_account_repo.create_account(
            line_id=line_id,
            channel_type=data.channel_type,
            credentials_encrypted={},
            expires_at=expires_at,
        )

        log.info(f"\n\n !!! ---- LineService.add_channel account {account} --- \n\n")

        if data.channel_type == ChannelType.WHATSAPP_GREEN:
            await self._allocate_whatsapp_instance(line_id)

        return ChannelAccountResponse(
            id=account.id,
            line_id=account.line_id,
            channel_type=account.channel_type,
            expires_at=account.expires_at,
        )

    async def renew_channel(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            data: ChannelRenew,
    ) -> ChannelAccountResponse:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        account = await self.channel_account_repo.get_by_line_and_type(line_id, data.channel_type)
        if not account:
            raise HTTPException(status_code=404, detail="Channel not found")

        '''
        if data.amount > 0:
            balance = await self.billing_repo.get_by_tenant(tenant_id)
            if balance.main_balance < data.amount:
                raise HTTPException(status_code=402, detail="Insufficient balance")
            log.info(f"\n\n self.billing_repo {type(self.billing_repo)} {dir(self.billing_repo)} \n\n")
            await self.billing_repo.deduct(tenant_id, data.amount)
            await self.ledger_repo.add_entry(
                tenant_id=tenant_id,
                amount=-data.amount,
                operation_type=LedgerOperationType.charge,
                reference_id=line_id,
                description=f"Продление канала {data.channel_type} на {data.subscription_period}",
            )
        '''

        now = datetime.now(timezone.utc)
        base = account.expires_at if account.expires_at and account.expires_at > now else now
        delta = timedelta(days=30) if data.subscription_period == SubscriptionPeriod.MONTH else timedelta(days=365)


        try:
            await self.line_repo.update_line(
                line=line,
                connection_state={"status": "connected"},
                status="active",
            )
        except Exception as e:
            log.error(f"\n\n!!!  --- ERROR --- can't update_line {line} {e} --- !!!\n\n")


        updated = await self.channel_account_repo.update_account(
            account,
            expires_at=base + delta,
        )

        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            expires_at=updated.expires_at,
        )


    async def create_line(
            self,
            tenant_id: uuid.UUID,
            data: LineCreate,
    ) -> LineResponse:
        line = await self.line_repo.create_line(
            tenant_id=tenant_id,
            name=data.name,
        )
        return LineResponse.model_validate(line)

    async def get_lines(self, tenant_id: uuid.UUID) -> list[LineListResponse]:
        rows = await self.line_repo.get_lines_with_expires(tenant_id)
        result = []
        for line, max_expires_at, channel_types in rows:
            days_until_expiry = None
            if max_expires_at:
                delta = max_expires_at - datetime.now(timezone.utc)
                days_until_expiry = max(0, delta.days)

            connection_status = "not_connected"
            if line.connection_state:
                connection_status = line.connection_state.get("status", "not_connected")

            result.append(LineListResponse.model_validate({
                **line.__dict__,
                "days_until_expiry": days_until_expiry,
                "connection_status": connection_status,
                "channel_types": [ct for ct in (channel_types or []) if ct is not None],
            }))
        log.info(f"LinesService.get_lines result {result}")
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

        accounts = await self.channel_account_repo.get_by_line(line_id)
        for account in accounts:
            print(f"account.channel_type {account.channel_type}")
            if account.channel_type == "whatsapp_green":
                instance = await self.instance_repo.get_instance_by_line(line.id)
                if instance:
                    await self.instance_repo.release_instance(instance)
                    log.info(f"Released instance {instance.external_id} from line {line.id}")

        await self.line_repo.delete_line(line)