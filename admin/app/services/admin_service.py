from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from app.repositories.admin_repo import (
    AdminTenantRepository,
    AdminLineRepository,
    AdminInstanceRepository,
    AdminBillingRepository
)
from models.lines import Line, Instance


class AdminService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.tenant_repo = AdminTenantRepository(session)
        self.line_repo = AdminLineRepository(session)
        self.instance_repo = AdminInstanceRepository(session)
        self.billing_repo = AdminBillingRepository(session)

    # --- Tenants ---
    async def block_tenant(self, tenant_id: UUID, reason: str):
        tenant = await self.tenant_repo.get(tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")
        await self.tenant_repo.block_tenant(tenant_id, reason)
        # TODO: Добавить логирование в Audit Log

    # --- Lines ---
    async def get_lines_global(self, skip: int, limit: int, filters: dict) -> List[Tuple[Line, str]]:
        return await self.line_repo.get_lines_with_tenant_names(skip, limit, filters)

    async def extend_line(self, line_id: UUID, days: int):
        from datetime import timedelta
        line = await self.line_repo.get(line_id)
        if not line:
            raise ValueError("Line not found")

        new_expires = line.expires_at or datetime.utcnow()
        new_expires += timedelta(days=days)

        await self.line_repo.extend_line(line_id, new_expires)

    # --- Instances ---
    async def clean_instance(self, instance_id: UUID, force: bool = False):
        instance = await self.instance_repo.get(instance_id)
        if not instance:
            raise ValueError("Instance not found")

        if instance.status != "idle" and not force:
            # В реальной реализации здесь вызов API провайдера для сброса сессии
            # Для MVP просто меняем статус, если force=True или он уже idle
            if instance.status == "allocated":
                # Логика принудительной отвязки
                pass

        await self.instance_repo.release_instance(instance_id)
        # TODO: Вызов внешней логики очистки сессии (GreenAPI/WABA)

    # --- Billing ---
    async def adjust_balance(
            self,
            tenant_id: UUID,
            amount: Decimal,
            balance_type: str,
            description: str,
            reference_id: Optional[UUID] = None
    ):
        if amount == 0:
            raise ValueError("Amount cannot be zero")

        tenant = await self.tenant_repo.get(tenant_id)
        if not tenant:
            raise ValueError("Tenant not found")

        return await self.billing_repo.create_adjustment(
            tenant_id=tenant_id,
            amount=float(amount),
            balance_type=balance_type,
            description=description,
            reference_id=reference_id
        )