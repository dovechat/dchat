"""Billing repository — Balance, BalanceLedger, Tariff."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.billing import Balance, BalanceLedger, LedgerOperationType, Tariff
from repo.base import BaseRepository

import logging
log = logging.getLogger("uvicorn.error")


class BalanceRepository(BaseRepository[Balance]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Balance, session)

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> Balance | None:
        result = await self.session.execute(
            select(Balance).where(Balance.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, tenant_id: uuid.UUID) -> Balance:
        balance = await self.get_by_tenant(tenant_id)
        if not balance:
            balance = Balance(
                tenant_id=tenant_id,
                main_balance=Decimal("0"),
                bonus_balance=Decimal("0"),
            )
            self.session.add(balance)
            await self.session.flush()
            await self.session.refresh(balance)
        return balance

    async def deduct(self, tenant_id: uuid.UUID, amount: Decimal, balance_type: str = "main") -> Balance:
        balance = await self.get_or_create(tenant_id)
        if balance_type == "bonus":
            balance.bonus_balance -= amount
        else:
            balance.main_balance -= amount
        await self.session.flush()
        await self.session.refresh(balance)
        return balance

    async def add(self, tenant_id: uuid.UUID, amount: Decimal, balance_type: str = "main") -> Balance:
        balance = await self.get_or_create(tenant_id)
        if balance_type == "bonus":
            balance.bonus_balance += amount
        else:
            balance.main_balance += amount
        await self.session.flush()
        await self.session.refresh(balance)
        return balance

    async def get_all_balances(self) -> list[Balance]:
        result = await self.session.execute(select(Balance))
        return list(result.scalars().all())


class BalanceLedgerRepository(BaseRepository[BalanceLedger]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(BalanceLedger, session)

    async def charge_exists(self, line_id: uuid.UUID, period_date: date) -> bool:
        """Idempotency check: has this line already been charged for this date?"""
        result = await self.session.execute(
            select(func.count())
            .select_from(BalanceLedger)
            .where(BalanceLedger.reference_id == line_id)
            .where(BalanceLedger.operation_type == LedgerOperationType.charge)
            .where(func.date(BalanceLedger.created_at) == period_date)
        )
        return result.scalar_one() > 0

    async def add_entry(
        self,
        tenant_id: uuid.UUID,
        amount: Decimal,
        operation_type: LedgerOperationType,
        reference_id: uuid.UUID | None = None,
        description: str | None = None,
        balance_type: str = "main",
    ) -> BalanceLedger:
        entry = BalanceLedger(
            tenant_id=tenant_id,
            amount=amount,
            balance_type=balance_type,
            operation_type=operation_type,
            reference_id=reference_id,
            description=description,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_tenant_ledger(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BalanceLedger]:
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"tenant_id": tenant_id},
        )


class TariffRepository(BaseRepository[Tariff]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tariff, session)

    async def get_active_by_channel_type(self, channel_type: str) -> Tariff | None:
        result = await self.session.execute(
            select(Tariff)
            .where(Tariff.channel_type == channel_type)
            .where(Tariff.is_active == True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    # стало
    async def get_daily_cost_by_tenant(self, tenant_id: uuid.UUID) -> Decimal:
        from models.lines import Line, LineStatus
        from models.channel_accounts import ChannelAccount

        stmt = (
            select(func.coalesce(func.sum(Tariff.price / Tariff.period_days), Decimal("0")))
            .join(ChannelAccount, func.cast(ChannelAccount.channel_type, String) == Tariff.channel_type)
            .join(Line, Line.id == ChannelAccount.line_id)
            .where(
                Tariff.is_active.is_(True),
                Line.tenant_id == tenant_id,
                Line.status.in_([LineStatus.active, LineStatus.expired]),
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or "0"))

    async def get_daily_cost_by_tenant_channels(self, tenant_id: uuid.UUID) -> Decimal:
        from models.lines import Line, LineStatus
        from models.channel_accounts import ChannelAccount
        from sqlalchemy import String
    
        stmt = (
            select(func.coalesce(func.sum(Tariff.price / Tariff.period_days), Decimal("0")))
            .join(ChannelAccount, func.cast(ChannelAccount.channel_type, String) == Tariff.channel_type)
            .join(Line, Line.id == ChannelAccount.line_id)
            .where(
                Tariff.is_active.is_(True),
                Line.tenant_id == tenant_id,
                Line.status.in_([LineStatus.active, LineStatus.expired]),
            )
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or "0"))