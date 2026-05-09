"""Pydantic schemas for admin service."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# Общее
# ---------------------------------------------------------------------------

class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(100, ge=1, le=500)


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Пользователи / тенанты
# ---------------------------------------------------------------------------

class UserStatus(str, Enum):
    trial = "trial"
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


class UserRole(str, Enum):
    admin = "admin"
    user = "user"
    support = "support"
    owner = "owner"


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserOut]
    total: int


class SetUserStatusRequest(BaseModel):
    status: UserStatus


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


# ---------------------------------------------------------------------------
# Линии
# ---------------------------------------------------------------------------

class LineStatus(str, Enum):
    active = "active"
    disabled = "disabled"
    expired = "expired"

class ChannelOut(BaseModel):
    id: uuid.UUID
    channel_type: str
    expires_at: datetime | None = None
    connection_status: str | None = None

    model_config = {"from_attributes": True}

class LineOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    status: LineStatus
    is_demo: bool
    created_at: datetime | None = None
    channels: list[ChannelOut] = []

    model_config = {"from_attributes": True}


class LineListResponse(BaseModel):
    items: list[LineOut]
    total: int


class SetLineStatusRequest(BaseModel):
    status: LineStatus


class ExtendLineRequest(BaseModel):
    days: int = Field(..., ge=1, le=3650, description="На сколько дней продлить")


# ---------------------------------------------------------------------------
# Инстансы Green API
# ---------------------------------------------------------------------------

class InstanceStatus(str, Enum):
    idle = "idle"
    allocated = "allocated"
    busy = "busy"
    error = "error"


class InstanceOut(BaseModel):
    id: uuid.UUID
    provider: str
    external_id: str
    status: InstanceStatus
    allocated_to_line_id: uuid.UUID | None = None
    last_cleanup_at: datetime | None = None
    health: dict | None = None
    line_name: str | None = None

    model_config = {"from_attributes": True}


class InstanceListResponse(BaseModel):
    items: list[InstanceOut]
    total: int
    idle_count: int
    allocated_count: int


class CreateInstanceRequest(BaseModel):
    provider: str = Field("green", description="green | waba")
    external_id: str = Field(..., description="ID инстанса у провайдера")
    token: str = Field("token", description="green auth token")

class BulkCleanRequest(BaseModel):
    instance_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Биллинг
# ---------------------------------------------------------------------------

class LedgerEntryOut(BaseModel):
    id: int
    tenant_id: uuid.UUID
    amount: Decimal
    balance_type: str
    operation_type: str
    description: str | None = None
    reference_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LedgerListResponse(BaseModel):
    items: list[LedgerEntryOut]
    total: int


class BalanceOut(BaseModel):
    main: float
    bonus: float


class AdjustmentRequest(BaseModel):
    amount: Decimal = Field(..., description="Положительное — пополнение, отрицательное — списание")
    balance_type: str = Field("main", pattern="^(main|bonus)$")
    description: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Аудит
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    id: int
    tenant_id: uuid.UUID | None = None
    user: str | None = None
    action: str
    entity_type: str | None = None
    entity_name: str | None = None
    old_state: dict | None = None
    new_state: dict | None = None
    ip_address: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int


# ---------------------------------------------------------------------------
# Статистика (дашборд)
# ---------------------------------------------------------------------------

class AdminStatsOut(BaseModel):
    total_users: int
    active_users: int
    blocked_users: int
    total_lines: int
    active_lines: int
    blocked_lines: int
    expired_lines: int
    total_instances: int
    idle_instances: int
    allocated_instances: int
    error_instances: int


class TenantShortOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


# === TARIFF SCHEMAS ===

class TariffCreate(BaseModel):
    name: str
    channel_type: str
    period_days: int = Field(..., ge=1)
    price: Decimal = Field(..., ge=0)
    is_active: bool = True

class TariffUpdate(BaseModel):
    name: str | None = None
    channel_type: str | None = None
    period_days: int | None = Field(None, ge=1)
    price: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None


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



# ---------------------------------------------------------------------------
# Тенанты
# ---------------------------------------------------------------------------

class TenantStatus(str, Enum):
    active = "active"
    blocked = "blocked"


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    status: TenantStatus
    payment: str | None = None
    locale: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantListResponse(BaseModel):
    items: list[TenantOut]
    total: int


class SetTenantStatusRequest(BaseModel):
    status: TenantStatus


class UpdateTenantRequest(BaseModel):
    name: str | None = None
    locale: str | None = None
    payment: str | None = None
    status: TenantStatus | None = None


class ReallocateRequest(BaseModel):
    line_id: uuid.UUID