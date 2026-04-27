import uuid
from decimal import Decimal
from fastapi import HTTPException
from app.repositories.billing_repo import (
    BalanceRepository,
    BalanceLedgerRepository,
    PaymentRepository,
    TariffRepository
)
from app.schemas.billing_schemas import (
    BalanceResponse,
    BalanceAdjust,
    BalanceLedgerResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentStatusUpdate,
    TariffCreate,
    TariffUpdate,
    TariffResponse
)
from models.billing import Payment
import logging

log = logging.getLogger("uvicorn.error")


class BillingService:

    def __init__(
            self,
            balance_repo: BalanceRepository,
            ledger_repo: BalanceLedgerRepository,
            payment_repo: PaymentRepository,
            tariff_repo: TariffRepository
    ):
        self.balance_repo = balance_repo
        self.ledger_repo = ledger_repo
        self.payment_repo = payment_repo
        self.tariff_repo = tariff_repo

    # === BALANCE ===

    async def get_balance(self, tenant_id: uuid.UUID) -> BalanceResponse:
        """Get current balance for tenant"""
        balance = await self.balance_repo.get_by_tenant(tenant_id)

        if not balance:
            balance = await self.balance_repo.create_balance(tenant_id)

        return BalanceResponse.model_validate(balance)

    async def adjust_balance(
            self,
            tenant_id: uuid.UUID,
            data: BalanceAdjust
    ) -> BalanceResponse:
        """Manual balance adjustment (admin operation)"""
        balance = await self.balance_repo.get_by_tenant(tenant_id)

        if not balance:
            balance = await self.balance_repo.create_balance(tenant_id)

        # Adjust balance
        updated_balance = await self.balance_repo.adjust_balance(
            balance,
            data.amount,
            data.balance_type
        )

        # Create ledger entry
        await self.ledger_repo.create_entry(
            tenant_id=tenant_id,
            amount=data.amount,
            balance_type=data.balance_type,
            description=data.description
        )

        return BalanceResponse.model_validate(updated_balance)

    async def get_ledger_history(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[BalanceLedgerResponse]:
        """Get balance ledger history"""
        entries = await self.ledger_repo.get_history(tenant_id, skip, limit)
        return [BalanceLedgerResponse.model_validate(e) for e in entries]

    # === PAYMENTS ===
    async def create_payment(self, tenant_id: uuid.UUID, data: "PaymentCreate") -> Payment:
        return await self.payment_repo.create(
            tenant_id=tenant_id,
            amount=data.amount,
            payment_method=data.payment_method,
            status="pending",
        )

    async def get_payments(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> list[PaymentResponse]:
        """Get payment history"""
        payments = await self.payment_repo.get_payments_by_tenant(tenant_id, skip, limit)
        return [PaymentResponse.model_validate(p) for p in payments]

    async def update_payment_status(
            self,
            payment_id: uuid.UUID,
            tenant_id: uuid.UUID,
            data: PaymentStatusUpdate
    ) -> PaymentResponse:
        """Update payment status manually (admin operation)"""
        payment = await self.payment_repo.get_by_id(payment_id, tenant_id=tenant_id)

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        updated_payment = await self.payment_repo.update_status(payment, data.status)

        return PaymentResponse.model_validate(updated_payment)

    # === TARIFFS ===

    async def get_tariffs(self) -> list[TariffResponse]:
        """Get all active tariffs"""
        tariffs = await self.tariff_repo.get_all_active()
        return [TariffResponse.model_validate(t) for t in tariffs]

    async def create_tariff(self, data: TariffCreate) -> TariffResponse:
        """Create new tariff"""
        print(f"****************** data {data}")
        tariff = await self.tariff_repo.create_tariff(
            name=data.name,
            channel_type=data.channel_type,
            period=data.period,
            price=data.price,
            is_active=data.is_active
        )
        return TariffResponse.model_validate(tariff)

    async def update_tariff(
            self,
            tariff_id: uuid.UUID,
            data: TariffUpdate
    ) -> TariffResponse:
        """Update tariff"""
        tariff = await self.tariff_repo.get_by_id(tariff_id)

        if not tariff:
            raise HTTPException(status_code=404, detail="Tariff not found")

        update_data = data.model_dump(exclude_unset=True)
        updated_tariff = await self.tariff_repo.update_tariff(tariff, **update_data)

        return TariffResponse.model_validate(updated_tariff)