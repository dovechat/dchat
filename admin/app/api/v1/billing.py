"""Admin API: billing and balance management."""
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdjustmentRequest,
    BalanceOut,
    LedgerListResponse,
    MessageResponse,
)
from app.services.billing_service import AdminBillingService

router = APIRouter(prefix="/billing", tags=["Admin — Billing"])


@router.get("/ledger", response_model=LedgerListResponse)
async def get_ledger(
    db: DBSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: UUID | None = Query(None),
    operation_type: str | None = Query(
        None,
        description="deposit | charge | adjustment | bonus_grant | refund",
    ),
    balance_type: str | None = Query(None, description="main | bonus"),
):
    """
    Журнал балансовых операций по всем тенантам.
    Поддерживает фильтрацию по тенанту, типу операции и типу баланса.
    """
    uow = AdminUnitOfWork(db)
    service = AdminBillingService(uow)
    return await service.get_ledger(
        skip=skip,
        limit=limit,
        tenant_id=tenant_id,
        operation_type=operation_type,
        balance_type=balance_type,
        actor_id=UUID(admin["sub"]),
    )


@router.get("/balance/{tenant_id}", response_model=BalanceOut)
async def get_tenant_balance(tenant_id: UUID, db: DBSession, admin: AdminUser):
    """Текущий баланс тенанта (main + bonus)."""
    uow = AdminUnitOfWork(db)
    service = AdminBillingService(uow)
    return await service.get_balance(tenant_id, actor_id=UUID(admin["sub"]))


@router.post("/adjustment/{tenant_id}", response_model=MessageResponse)
async def create_adjustment(
    tenant_id: UUID,
    request: AdjustmentRequest,
    db: DBSession,
    admin: AdminUser,
):
    """
    Ручная корректировка баланса тенанта администратором.
    Положительный amount — пополнение, отрицательный — списание.
    Фиксируется в ledger как operation_type=adjustment с reference_id=admin_id.
    """
    uow = AdminUnitOfWork(db)
    service = AdminBillingService(uow)
    return await service.create_adjustment(
        tenant_id=tenant_id,
        request=request,
        actor_id=UUID(admin["sub"]),
    )