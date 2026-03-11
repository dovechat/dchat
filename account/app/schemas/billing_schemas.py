import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# === BALANCE SCHEMAS ===

class BalanceResponse(BaseModel):
    """Current balance for tenant"""
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    main_balance: Decimal
    bonus_balance: Decimal
    updated_at: datetime | None = datetime.now(timezone.utc)


class BalanceAdjust(BaseModel):
    """Manual balance adjustment by admin"""
    amount: Decimal = Field(..., description="Positive for credit, negative for debit")
    balance_type: str = Field("main", description="main or bonus")
    description: str = Field(..., min_length=1, max_length=500)


# === LEDGER SCHEMAS ===

class BalanceLedgerResponse(BaseModel):
    """Single ledger entry"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: uuid.UUID
    amount: Decimal
    balance_type: str
    description: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    created_at: datetime | None = datetime.now(timezone.utc)


# === PAYMENT SCHEMAS ===

class PaymentResponse(BaseModel):
    """Payment history entry"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    amount: Decimal
    status: str
    payment_method: Optional[str] = None
    external_id: Optional[str] = None
    created_at: datetime | None = datetime.now(timezone.utc)
    updated_at: datetime | None = datetime.now(timezone.utc)


class PaymentStatusUpdate(BaseModel):
    """Update payment status manually"""
    status: str = Field(..., description="paid, failed, pending, refunded")


# === TARIFF SCHEMAS ===

class TariffCreate(BaseModel):
    """Create new tariff"""
    name: str = Field(..., description="name of the tariff")
    channel_type: str = Field(..., description="whatsapp_green, telegram_bot, etc")
    period: int = Field(..., description="number of days")
    price: Decimal = Field(..., ge=0)
    is_active: bool = Field(True)


class TariffUpdate(BaseModel):
    """Update tariff"""
    price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class TariffResponse(BaseModel):
    """Tariff info"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel_type: str
    period_days: int
    price: Decimal
    is_active: bool
    created_at: datetime | None = datetime.now(timezone.utc)
    updated_at: datetime | None = datetime.now(timezone.utc)