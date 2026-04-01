from datetime import datetime
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Any
from uuid import UUID

from repo.base import BaseRepository
from models.tenants import Tenant, User
from models.lines import Line, Instance
from models.billing import BalanceLedger, LedgerOperationType


class AdminTenantRepository(BaseRepository[Tenant]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Tenant, session=session)

    async def block_tenant(self, tenant_id: UUID, reason: str) -> None:
        stmt = update(Tenant).where(Tenant.id == tenant_id).values(
            status="blocked"
            # Если есть поле block_reason, добавить сюда
        )
        await self.session.execute(stmt)


class AdminLineRepository(BaseRepository[Line]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Line, session=session)

    async def get_lines_with_tenant_names(
            self,
            skip: int = 0,
            limit: int = 50,
            filters: Optional[dict] = None
    ) -> List[Any]:
        # Сложный запрос с JOIN для получения имени тенанта
        query = select(Line, Tenant.name.label("tenant_name")).join(Tenant, Line.tenant_id == Tenant.id)

        if filters:
            for key, value in filters.items():
                if hasattr(Line, key):
                    query = query.where(getattr(Line, key) == value)
                elif hasattr(Tenant, key):
                    query = query.where(getattr(Tenant, key) == value)

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.all()  # Возвращает кортежи (Line, tenant_name)

    async def extend_line(self, line_id: UUID, new_expires_at: datetime) -> None:
        stmt = update(Line).where(Line.id == line_id).values(
            expires_at=new_expires_at,
            status="active"
        )
        await self.session.execute(stmt)


class AdminInstanceRepository(BaseRepository[Instance]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Instance, session=session)

    async def release_instance(self, instance_id: UUID) -> None:
        stmt = update(Instance).where(Instance.id == instance_id).values(
            status="idle",
            allocated_to_line_id=None
        )
        await self.session.execute(stmt)


class AdminBillingRepository(BaseRepository[BalanceLedger]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=BalanceLedger, session=session)

    async def create_adjustment(
            self,
            tenant_id: UUID,
            amount: float,
            balance_type: str,
            description: str,
            reference_id: Optional[UUID] = None
    ) -> BalanceLedger:
        entry = BalanceLedger(
            tenant_id=tenant_id,
            amount=amount,
            balance_type=balance_type,
            operation_type=LedgerOperationType.adjustment,
            description=description,
            reference_id=reference_id
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry