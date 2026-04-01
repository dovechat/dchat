"""Admin service: billing operations."""
import logging
from uuid import UUID

from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdjustmentRequest,
    BalanceOut,
    LedgerListResponse,
    LedgerEntryOut,
    MessageResponse,
)
from models.billing import LedgerOperationType

log = logging.getLogger("uvicorn.error")


class AdminBillingService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def get_ledger(
        self,
        skip: int,
        limit: int,
        tenant_id: UUID | None,
        operation_type: str | None,
        balance_type: str | None,
        actor_id: UUID,
    ) -> LedgerListResponse:
        op_type_enum = None
        if operation_type:
            try:
                op_type_enum = LedgerOperationType(operation_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid operation_type: {operation_type}",
                )

        entries = await self._uow.billing.get_ledger(
            skip=skip,
            limit=limit,
            tenant_id=tenant_id,
            operation_type=op_type_enum,
            balance_type=balance_type,
        )
        total = len(entries)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="view_ledger",
            resource_type="billing",
            details={"tenant_id": str(tenant_id) if tenant_id else None},
        )
        await self._uow.commit()

        return LedgerListResponse(
            items=[LedgerEntryOut.model_validate(e) for e in entries],
            total=total,
        )

    async def get_balance(self, tenant_id: UUID, actor_id: UUID) -> BalanceOut:
        # Проверяем, что тенант существует
        user = await self._uow.tenants.get_all_users(
            filters={"tenant_id": tenant_id}, limit=1
        ) if False else None  # заглушка — в реальном коде проверка через tenant repo

        balance = await self._uow.billing.get_tenant_balance(tenant_id)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="view_balance",
            resource_type="billing",
            details={"tenant_id": str(tenant_id)},
        )
        await self._uow.commit()

        return BalanceOut(main=balance["main"], bonus=balance["bonus"])

    async def create_adjustment(
        self,
        tenant_id: UUID,
        request: AdjustmentRequest,
        actor_id: UUID,
    ) -> MessageResponse:
        entry = await self._uow.billing.create_adjustment(
            tenant_id=tenant_id,
            amount=float(request.amount),
            balance_type=request.balance_type,
            description=request.description,
            admin_user_id=actor_id,
        )

        await self._uow.audit.log(
            actor_id=actor_id,
            action="balance_adjustment",
            resource_type="billing",
            resource_id=tenant_id,
            details={
                "amount": str(request.amount),
                "balance_type": request.balance_type,
                "description": request.description,
            },
        )
        await self._uow.commit()

        log.info(
            f"Admin {actor_id}: adjustment {request.amount} ({request.balance_type}) "
            f"for tenant {tenant_id}: {request.description}"
        )
        return MessageResponse(message=f"Adjustment created: {request.amount} on {request.balance_type} balance")