import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from fastapi import Depends, HTTPException
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext

from app.repositories.billing_repo import (
    PaymentRepository,
    TariffRepository
)
from app.repositories.tenant_repo import RequisitsRepository, TenantRepository
from app.repositories.line_repo import  LineRepository
from repo.instance_repo import InstanceRepository
from repo.crm_settings_repo import CrmSettingsRepository
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from repo.user import UserRepository
from services.cleanup_service import CleanupService
from app.repositories.billing_repo import BalanceLedgerRepository, BalanceRepository
from repo.line_repo import ChannelAccountRepository
from app.services.channel_service import ChannelAccountService
from app.services.line_service import LineService
from app.core.uow import TenantMembershipUoW
from app.services.webhook_service import WebhookService



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

async def get_instance_repo(db: AsyncSession = Depends(get_db)) -> InstanceRepository:
    return InstanceRepository(db)

async def get_channel_service(
    channel_repo: ChannelAccountRepository = Depends(get_channel_account_repo),
    line_repo: LineRepository = Depends(get_line_repo),
    instance_repo: InstanceRepository = Depends(get_instance_repo)
) -> ChannelAccountService:
    return ChannelAccountService(channel_repo, line_repo, instance_repo)

async def get_conversation_repo(db: AsyncSession = Depends(get_db)) -> ConversationRepository:
    return ConversationRepository(db)

async def get_message_repo(db: AsyncSession = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)

async def get_cleanup_service(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    message_repo: MessageRepository = Depends(get_message_repo),
    channel_account_repo: ChannelAccountRepository = Depends(get_channel_account_repo),
    instance_repo: InstanceRepository = Depends(get_instance_repo),
) -> CleanupService:
    return CleanupService(conversation_repo, message_repo, channel_account_repo, instance_repo)

async def get_tenant_uow(session: AsyncSession = Depends(get_db)) -> TenantMembershipUoW:
    return TenantMembershipUoW(session)

# ------- tenants
async def get_tenant_repo(db: AsyncSession = Depends(get_db)) -> TenantRepository:
    """Get tenant repository instance."""
    return TenantRepository(db)

def get_crm_settings_repo(db: AsyncSession = Depends(get_db)) -> CrmSettingsRepository:
    return CrmSettingsRepository(db)

def check_tenant_access(tenant_id: uuid.UUID, current_user: UserContext = Depends(get_current_user)):
    if current_user.role == 'admin':
        return tenant_id
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Token tenant_id mismatch")
    if current_user.member not in ('owner', 'admin', 'member'):
        raise HTTPException(status_code=403, detail="No membership in tenant")
    return tenant_id

async def get_requisits_repo(db: AsyncSession = Depends(get_db)) -> RequisitsRepository:
    """Get requisits repository instance."""
    return RequisitsRepository(db)


# ------- lines
async def get_billing_repo(db: AsyncSession = Depends(get_db)) -> BalanceRepository:
    return BalanceRepository(db)

async def ledger_repo(db: AsyncSession = Depends(get_db)) -> BalanceLedgerRepository:
    return BalanceLedgerRepository(db)

async def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)

async def get_line_service(
    billing_repo: BalanceRepository = Depends(get_billing_repo),
    ledger_repo: BalanceLedgerRepository = Depends(get_ledger_repo),
    line_repo: LineRepository = Depends(get_line_repo),
    instance_repo: InstanceRepository = Depends(get_instance_repo),
    channel_account_repo: ChannelAccountRepository = Depends(get_channel_account_repo),
    user_repo: UserRepository = Depends(get_user_repo),
) -> LineService:
    return LineService(billing_repo, ledger_repo, line_repo, instance_repo, channel_account_repo, user_repo)

async def get_webhook_service():
    async for session in get_db():
        line_repo = LineRepository(session)
        channel_repo = ChannelAccountRepository(session)
        yield WebhookService(line_repo, channel_repo)
        break