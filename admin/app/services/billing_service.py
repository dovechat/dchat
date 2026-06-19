"""Admin service: billing operations."""
import uuid
import logging

from decimal import Decimal
from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdjustmentRequest,
    BalanceOut,
    LedgerListResponse,
    LedgerEntryOut,
    MessageResponse,
    TariffCreate,
    TariffResponse,
    TariffUpdate,
)
from models.billing import LedgerOperationType
from models.tenants import UserStatus

log = logging.getLogger("uvicorn.error")


class AdminBillingService:

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    async def get_ledger(
        self,
        skip: int,
        limit: int,
        tenant_id: uuid.UUID | None,
        operation_type: str | None,
        balance_type: str | None,
        actor_id: uuid.UUID,
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

        return LedgerListResponse(
            items=[LedgerEntryOut.model_validate(e) for e in entries],
            total=total,
        )

    async def get_balance(self, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> BalanceOut:
        # Check if the tenant exists
        user = await self._uow.users.get_all_users(
            filters={"tenant_id": tenant_id}, limit=1
        ) if False else None  # заглушка — в реальном коде проверка через tenant repo
        balance = await self._uow.balance.get_by_tenant(tenant_id)
        return BalanceOut(main=balance.main_balance, bonus=balance.bonus_balance)

    async def create_adjustment(
            self,
            tenant_id: uuid.UUID,
            request: AdjustmentRequest,
            actor_id: uuid.UUID,
    ) -> MessageResponse:
        # get current balance
        balance = await self._uow.balance.get_by_tenant(tenant_id)
        new_main = balance.main_balance + Decimal(
            str(request.amount)) if request.balance_type == "main" else balance.main_balance
        new_bonus = balance.bonus_balance + Decimal(
            str(request.amount)) if request.balance_type == "bonus" else balance.bonus_balance

        # check if icoming amount is anough to give a bonus 
        if request.amount >= 10000:
            new_bonus += Decimal(str(request.amount)) * Decimal("0.1")
        await self._uow.billing.update(balance, main_balance=new_main, bonus_balance=new_bonus)

        # add record to bliilng log
        await self._uow.billing.create_adjustment(
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
        if request.amount > 0:
            memberships = await self._uow.memberships.get_multi(
                filters={"tenant_id": tenant_id, "role": "owner", "is_active": True}
            )
            # update user status from trial
            for m in memberships:
                user = await self._uow.users.get_by_id(m.user_id)
                if user and user.status == "trial":
                    await self._uow.users.update(user, status="active")
        await self._uow.commit()

        log.info(
            f"Admin {actor_id}: adjustment {request.amount} ({request.balance_type}) "
            f"for tenant {tenant_id}: {request.description}"
        )
        return MessageResponse(message=f"Adjustment created: {request.amount} on {request.balance_type} balance")


    async def get_tenants(self):
        return await self._uow.tenants.get_multi(limit=1000, order_by=[('name', 'asc')])

# === TARIFFS ===

    async def get_tariffs(self) -> list[TariffResponse]:
        """Get all active tariffs"""
        tariffs = await self._uow.tariff.get_all_active()
        return [TariffResponse.model_validate(t) for t in tariffs]

    async def create_tariff(self, data: TariffCreate, actor_id: uuid.UUID,) -> TariffResponse:
        """Create new tariff"""
        print(f"****************** data {data}")
        tariff = await self._uow.tariff.create_tariff(
            name=data.name,
            channel_type=data.channel_type,
            period_days=data.period_days,
            price=data.price,
            is_active=data.is_active
        )

        await self._uow.audit.log(
            actor_id=actor_id,
            action="new",
            resource_type="tariff",
            resource_id=tariff.id,
            details={"tariff_id": str(tariff.id)},
        )

        return TariffResponse.model_validate(tariff)

    async def update_tariff(
            self,
            tariff_id: uuid.UUID,
            data: TariffUpdate,
            actor_id: uuid.UUID,
    ) -> TariffResponse:
        """Update tariff"""
        tariff = await self._uow.tariff.get_by_id(tariff_id)

        if not tariff:
            raise HTTPException(status_code=404, detail="Tariff not found")

        update_data = data.model_dump(exclude_unset=True)
        updated_tariff = await self._uow.tariff.update_tariff(tariff, **update_data)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="update_tariff",
            resource_type="tariff",
            resource_id=tariff_id,
            details={"tariff_id": str(tariff_id)},
        )

        return TariffResponse.model_validate(updated_tariff)


    async def delete_tariff(
            self,
            tariff_id: uuid.UUID,
            actor_id: uuid.UUID,
    ) -> None:
        tariff = await self._uow.tariff.get_by_id(tariff_id)
        if not tariff:
            raise ValueError("Тариф не найден")
        await self._uow.tariff.delete(tariff)

        await self._uow.audit.log(
            actor_id=actor_id,
            action="delete_tariff",
            resource_type="tariff",
            resource_id=tariff_id,
            details={"tariff_id": str(tariff_id)},
        )

        await self._uow.commit()
