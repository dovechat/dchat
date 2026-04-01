"""Admin repository for billing (balance ledger, payments)."""
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repo.base import BaseRepository
from models.billing import BalanceLedger, LedgerOperationType


class AdminBillingRepository(BaseRepository[BalanceLedger]):
    """Репозиторий журнала балансовых операций."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(BalanceLedger, session)

    async def get_ledger(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: UUID | None = None,
        operation_type: LedgerOperationType | None = None,
        balance_type: str | None = None,
    ) -> list[BalanceLedger]:
        filters: dict[str, Any] = {}
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if operation_type:
            filters["operation_type"] = operation_type
        if balance_type:
            filters["balance_type"] = balance_type
        return await self.get_multi(skip=skip, limit=limit, filters=filters)

    async def create_adjustment(
        self,
        tenant_id: UUID,
        amount: float,
        balance_type: str,
        description: str,
        admin_user_id: UUID,
    ) -> BalanceLedger:
        """
        Ручная корректировка баланса администратором.
        operation_type = adjustment, reference_id = admin_user_id для трассировки.
        """
        return await self.create(
            tenant_id=tenant_id,
            amount=amount,
            balance_type=balance_type,
            operation_type=LedgerOperationType.adjustment,
            description=description,
            reference_id=admin_user_id,
        )

    async def get_tenant_balance(self, tenant_id: UUID) -> dict[str, float]:
        """
        Суммирует операции из ledger и возвращает текущий баланс.
        Отдельно по main и bonus.
        """
        entries = await self.get_multi(
            limit=10_000,
            filters={"tenant_id": tenant_id},
        )
        main_balance = sum(
            float(e.amount) for e in entries if e.balance_type == "main"
        )
        bonus_balance = sum(
            float(e.amount) for e in entries if e.balance_type == "bonus"
        )
        return {"main": main_balance, "bonus": bonus_balance}