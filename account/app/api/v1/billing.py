import uuid
from fastapi import APIRouter, Depends, status, Query
from fastapi.security import HTTPBearer
from core.dependencies import get_current_user
from app.core.dependencies import check_tenant_access, get_billing_service
from app.schemas.billing_schemas import (
    BalanceResponse,
    BalanceAdjust,
    BalanceLedgerResponse,
    PaymentResponse,
    PaymentStatusUpdate,
    TariffCreate,
    TariffUpdate,
    TariffResponse
)
from app.services.billing_service import BillingService
from schemas.auth_schemas import UserContext
import logging

log = logging.getLogger("uvicorn.error")
auth_scheme = HTTPBearer()

billing_router = APIRouter(
    tags=["Billing"],
    prefix="/tenants/{tenant_id}/billing",
    dependencies=[Depends(auth_scheme)]
)

tariff_router = APIRouter(
    tags=["Tariffs"],
    prefix="/tariffs",
    dependencies=[Depends(auth_scheme)]
)


# === BALANCE ENDPOINTS ===

@billing_router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    billing_service: BillingService = Depends(get_billing_service)
) -> BalanceResponse:
    """Get current balance"""
    return await billing_service.get_balance(tenant_id)


@billing_router.post("/balance/adjust", response_model=BalanceResponse)
async def adjust_balance(
    data: BalanceAdjust,
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    billing_service: BillingService = Depends(get_billing_service)
) -> BalanceResponse:
    """Manual balance adjustment (admin only)"""
    return await billing_service.adjust_balance(tenant_id, data)


@billing_router.get("/balance/history", response_model=list[BalanceLedgerResponse])
async def get_ledger_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    billing_service: BillingService = Depends(get_billing_service)
) -> list[BalanceLedgerResponse]:
    """Get balance ledger history"""
    return await billing_service.get_ledger_history(tenant_id, skip, limit)


# === PAYMENT ENDPOINTS ===

@billing_router.get("/payments", response_model=list[PaymentResponse])
async def get_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    billing_service: BillingService = Depends(get_billing_service)
) -> list[PaymentResponse]:
    """Get payment history"""
    return await billing_service.get_payments(tenant_id, skip, limit)


@billing_router.patch("/payments/{payment_id}", response_model=PaymentResponse)
async def update_payment_status(
    payment_id: uuid.UUID,
    data: PaymentStatusUpdate,
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    billing_service: BillingService = Depends(get_billing_service)
) -> PaymentResponse:
    """Update payment status manually (admin only)"""
    return await billing_service.update_payment_status(payment_id, tenant_id, data)


# === TARIFF ENDPOINTS ===

@tariff_router.get("/", response_model=list[TariffResponse])
async def get_tariffs(
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> list[TariffResponse]:
    """Get all active tariffs"""
    return await billing_service.get_tariffs()


@tariff_router.post("/", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
async def create_tariff(
    data: TariffCreate,
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Create new tariff (admin only)"""
    return await billing_service.create_tariff(data)


@tariff_router.patch("/{tariff_id}", response_model=TariffResponse)
async def update_tariff(
    tariff_id: uuid.UUID,
    data: TariffUpdate,
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Update tariff (admin only)"""
    return await billing_service.update_tariff(tariff_id, data)