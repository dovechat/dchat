"""Admin API: billing and balance management."""
import uuid

from fastapi import APIRouter, Depends, status, Query
from fastapi.security import HTTPBearer

from app.core.dependencies import AdminUser, DBSession, get_billing_service
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    AdjustmentRequest,
    BalanceOut,
    LedgerListResponse,
    MessageResponse,
    TenantShortOut,
    TariffCreate,
    TariffUpdate,
    TariffResponse
)
from app.services.billing_service import AdminBillingService
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext

router = APIRouter(prefix="/billing", tags=["Admin — Billing"])
auth_scheme = HTTPBearer()

tariff_router = APIRouter(
    tags=["Tariffs"],
    prefix="/tariffs",
    dependencies=[Depends(auth_scheme)],
    redirect_slashes=False,
)

@router.get("/ledger", response_model=LedgerListResponse)
async def get_ledger(
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: uuid.UUID | None = Query(None),
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
    return await billing_service.get_ledger(
        skip=skip,
        limit=limit,
        tenant_id=tenant_id,
        operation_type=operation_type,
        balance_type=balance_type,
        actor_id=uuid.UUID(admin["sub"]),
    )


@router.get("/balance/{tenant_id}", response_model=BalanceOut)
async def get_tenant_balance(
    tenant_id: uuid.UUID,
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
):
    """Текущий баланс тенанта (main + bonus)."""
    return await billing_service.get_balance(tenant_id, actor_id=uuid.UUID(admin["sub"]))


@router.post("/adjustment/{tenant_id}", response_model=MessageResponse)
async def create_adjustment(
    tenant_id: uuid.UUID,
    request: AdjustmentRequest,
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
):
    """
    Ручная корректировка баланса тенанта администратором.
    Положительный amount — пополнение, отрицательный — списание.
    Фиксируется в ledger как operation_type=adjustment с reference_id=admin_id.
    """
    return await billing_service.create_adjustment(
        tenant_id=tenant_id,
        request=request,
        actor_id=uuid.UUID(admin["sub"]),
    )

@router.get("/tenants", response_model=list[TenantShortOut])
async def list_tenants(
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
):
    return await billing_service.get_tenants()



# === TARIFF ENDPOINTS ===

@tariff_router.get("", response_model=list[TariffResponse])
async def get_tariffs(
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
) -> list[TariffResponse]:
    """Get all active tariffs"""
    return await billing_service.get_tariffs()


@tariff_router.post("", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
async def create_tariff(
    data: TariffCreate,
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Create new tariff (admin only)"""
    return await billing_service.create_tariff(data, actor_id=uuid.UUID(admin["sub"]),)


@tariff_router.patch("/{tariff_id}", response_model=TariffResponse)
async def update_tariff(
    tariff_id: uuid.UUID,
    data: TariffUpdate,
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Update tariff (admin only)"""
    return await billing_service.update_tariff(tariff_id, data, actor_id=uuid.UUID(admin["sub"]),)


@tariff_router.delete("/{tariff_id}", status_code=204)
async def delete_tariff(
    tariff_id: uuid.UUID,
    admin: AdminUser,
    billing_service: AdminBillingService = Depends(get_billing_service)
):
    await billing_service.delete_tariff(tariff_id, actor_id=uuid.UUID(admin["sub"]),)

