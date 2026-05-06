"""Admin service: billing operations."""
import uuid
import logging
1
from fastapi import HTTPException, status

from app.core.uow import AdminUnitOfWork
from app.repositories.billing_repo import TariffRepository
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

    def __init__(self, uow: AdminUnitOfWork, tariff_repo: TariffRepository) -> None:
        self._uow = uow
        self.tariff_repo = tariff_repo

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

    async def get_balance(self, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> BalanceOut:
        # Проверяем, что тенант существует
        user = await self._uow.users.get_all_users(
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
        tenant_id: uuid.UUID,
        request: AdjustmentRequest,
        actor_id: uuid.UUID,
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
        if request.amount > 0:
            memberships = await self._uow.memberships.get_multi(
                filters={"tenant_id": tenant_id, "role": "owner", "is_active": True}
            )
            for m in memberships:
                user = await self._uow.users.get_by_id(m.user_id)
                if user and user.status == "trial":
                    await self._uow.users.update(user, status="active")
            await self._uow.commit()
        await self._uow.users.update(user, status=UserStatus.active)
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
        tariffs = await self.tariff_repo.get_all_active()
        return [TariffResponse.model_validate(t) for t in tariffs]

    async def create_tariff(self, data: TariffCreate) -> TariffResponse:
        """Create new tariff"""
        print(f"****************** data {data}")
        tariff = await self.tariff_repo.create_tariff(
            name=data.name,
            channel_type=data.channel_type,
            period_days=data.period_days,
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


    async def delete_tariff(self, tariff_id: uuid.UUID) -> None:
        tariff = await self.tariff_repo.get_by_id(tariff_id)
        if not tariff:
            raise ValueError("Тариф не найден")
        await self.tariff_repo.delete(tariff)