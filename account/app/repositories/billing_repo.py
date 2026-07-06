import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from models.billing import Balance, BalanceLedger, Payment, Tariff
from repo.base import BaseRepository
import logging

log = logging.getLogger("uvicorn.error")


class BalanceRepository(BaseRepository[Balance]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Balance, session)

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> Balance | None:
        """Get balance for tenant"""
        query = select(Balance).where(Balance.tenant_id == tenant_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_balance(self, tenant_id: uuid.UUID) -> Balance:
        """Create initial balance for new tenant"""
        return await self.create(
            tenant_id=tenant_id,
            main_balance=Decimal("0.00"),
            bonus_balance=Decimal("0.00")
        )

    async def adjust_balance(
            self,
            balance: Balance,
            amount: Decimal,
            balance_type: str = "main"
    ) -> Balance:
        """Adjust balance (add or subtract)"""
        if balance_type == "main":
            new_balance = balance.main_balance + amount
            return await self.update(balance, main_balance=new_balance)
        else:
            new_balance = balance.bonus_balance + amount
            return await self.update(balance, bonus_balance=new_balance)


class BalanceLedgerRepository(BaseRepository[BalanceLedger]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(BalanceLedger, session)

    async def create_entry(
            self,
            tenant_id: uuid.UUID,
            amount: Decimal,
            balance_type: str,
            description: str,
            operation_type: str,
            reference_id: Optional[uuid.UUID] = None,
    ) -> BalanceLedger:
        """Create ledger entry"""
        return await self.create(
            tenant_id=tenant_id,
            amount=amount,
            balance_type=balance_type,
            description=description,
            reference_id=reference_id,
            operation_type=operation_type
        )

    async def get_history(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[BalanceLedger]:
        """Get ledger history for tenant"""
        query = select(BalanceLedger).where(
            BalanceLedger.tenant_id == tenant_id
        ).order_by(desc(BalanceLedger.created_at)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_adjustments_by_tenant(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100):
        return await self.get_multi(
            skip=skip,
            limit=limit,
            filters={"tenant_id": tenant_id, "operation_type": "adjustment"},
            order_by=[("created_at", "desc")]
        )


class PaymentRepository(BaseRepository[Payment]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Payment, session)

    async def get_payments_by_tenant(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[Payment]:
        """Get payment history for tenant"""
        query = select(Payment).where(
            Payment.tenant_id == tenant_id
        ).order_by(desc(Payment.created_at)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
            self,
            payment: Payment,
            status: str
    ) -> Payment:
        """Update payment status"""
        return await self.update(payment, status=status)


class TariffRepository(BaseRepository[Tariff]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tariff, session)

    '''
    async def get_all_active(self) -> list[Tariff]:
        """Get all active tariffs"""
        query = select(Tariff).where(Tariff.is_active == True)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    '''

    async def get_all_active(self) -> list[Tariff]:
        """Get all active tariffs"""
        res = await self.get_multi(
            skip=0,
            limit=100,
            filters={"is_active": True},
            order_by=[('name', 'asc')]
        )
        # res = sorted(res, key = lambda x: x.name)
        return res

    async def get_by_channel_and_period(
            self,
            channel_type: str,
            period: str
    ) -> Tariff | None:
        """Get tariff by channel type and period"""
        query = select(Tariff).where(
            Tariff.channel_type == channel_type,
            Tariff.period_days == period,
            Tariff.is_active == True
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_tariff(
            self,
            name: str,
            channel_type: str,
            period: str,
            price: Decimal,
            is_active: bool = True
    ) -> Tariff:
        """Create new tariff"""
        return await self.create(
            name=name,
            channel_type=channel_type,
            period_days=period,
            price=price,
            is_active=is_active
        )

    async def update_tariff(
            self,
            tariff: Tariff,
            **data
    ) -> Tariff:
        """Update tariff"""
        return await self.update(tariff, **data)