import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from fastapi import Depends
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext
from app.repositories.billing_repo import (
    BalanceRepository,
    BalanceLedgerRepository,
    PaymentRepository,
    TariffRepository
)
from app.repositories.tenant_repo import RequisitsRepository, TenantRepository
from app.repositories.line_repo import (
    LineRepository,
    InstanceRepository,
    ChannelAccountRepository
)
from app.services.channel_service import ChannelAccountService
from app.services.line_service import LineService
from app.core.uow import TenantMembershipUoW

import logging
log = logging.getLogger("uvicorn.error")


# ------- billing
from app.services.billing_service import BillingService


async def get_balance_repo(db: AsyncSession = Depends(get_db)) -> BalanceRepository:
    return BalanceRepository(db)


async def get_ledger_repo(db: AsyncSession = Depends(get_db)) -> BalanceLedgerRepository:
    return BalanceLedgerRepository(db)


async def get_payment_repo(db: AsyncSession = Depends(get_db)) -> PaymentRepository:
    return PaymentRepository(db)


async def get_tariff_repo(db: AsyncSession = Depends(get_db)) -> TariffRepository:
    return TariffRepository(db)


async def get_billing_service(
    balance_repo: BalanceRepository = Depends(get_balance_repo),
    ledger_repo: BalanceLedgerRepository = Depends(get_ledger_repo),
    payment_repo: PaymentRepository = Depends(get_payment_repo),
    tariff_repo: TariffRepository = Depends(get_tariff_repo)
) -> BillingService:
    return BillingService(balance_repo, ledger_repo, payment_repo, tariff_repo)

# ------- channels
async def get_line_repo(db: AsyncSession = Depends(get_db)) -> LineRepository:
    return LineRepository(db)

async def get_channel_account_repo(db: AsyncSession = Depends(get_db)) -> ChannelAccountRepository:
    return ChannelAccountRepository(db)

async def get_channel_service(
    channel_repo: ChannelAccountRepository = Depends(get_channel_account_repo),
    line_repo: LineRepository = Depends(get_line_repo)
) -> ChannelAccountService:
    return ChannelAccountService(channel_repo, line_repo)

async def get_tenant_uow(session: AsyncSession = Depends(get_db)) -> TenantMembershipUoW:
    return TenantMembershipUoW(session)

# ------- tenants
async def get_tenant_repo(db: AsyncSession = Depends(get_db)) -> TenantRepository:
    """Get tenant repository instance."""
    return TenantRepository(db)

def check_tenant_access(tenant_id: uuid.UUID, current_user: UserContext = Depends(get_current_user)):
    log.info(f"******** service lines tenant_id {tenant_id} -- current_user.tenant_id {current_user.tenant_id}")
    if current_user.tenant_id != tenant_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Token tenant_id mismatch")
    return tenant_id

async def get_requisits_repo(db: AsyncSession = Depends(get_db)) -> RequisitsRepository:
    """Get requisits repository instance."""
    return RequisitsRepository(db)


# ------- lines
async def get_line_repo(db: AsyncSession = Depends(get_db)) -> LineRepository:
    return LineRepository(db)

async def get_instance_repo(db: AsyncSession = Depends(get_db)) -> InstanceRepository:
    return InstanceRepository(db)

async def get_channel_account_repo(db: AsyncSession = Depends(get_db)) -> ChannelAccountRepository:
    return ChannelAccountRepository(db)

async def get_line_service(
    line_repo: LineRepository = Depends(get_line_repo),
    instance_repo: InstanceRepository = Depends(get_instance_repo),
    channel_account_repo: ChannelAccountRepository = Depends(get_channel_account_repo)
) -> LineService:
    return LineService(line_repo, instance_repo, channel_account_repo)