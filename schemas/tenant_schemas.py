import uuid

from enum import Enum
from typing import Annotated, Optional
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class TenantStatus(str, Enum):
    """User roles in organization"""

    ACTIVE = "active"
    BLOCKED = "blocked"

class TenantPayment(str, Enum):
    """User roles in organization"""

    AQUIRING = "acquiring"
    WIRE = "wire"


class BankDetailsCreate(BaseModel):
    bank_name: str = Field(..., max_length=255)
    account_number: str = Field(..., min_length=20, max_length=20)
    bic: str = Field(..., min_length=9, max_length=9)
    corr_account: str = Field(..., min_length=20, max_length=20)
    kpp: str | None = Field(None, min_length=9, max_length=9)
    currency: str = Field("RUB", max_length=3)
    is_primary: bool = Field(True)

    @field_validator("account_number", "bic", "corr_account", "kpp")
    @classmethod
    def validate_digits(cls, v: str | None) -> str | None:
        if v and not v.isdigit():
            raise ValueError("Field must contain only digits")
        return v

class BankDetailsRUUpdate(BankDetailsCreate):
    """Inherits all fields and validators from BankDetailsCreate"""
    pass


class Tenant(BaseModel):
    """Base model for other types of tenant"""
    name: str = Field(..., min_length=1, max_length=255)
    locale: str = Field("en_US", max_length=10)
    payment: TenantPayment = TenantPayment.AQUIRING
    status: TenantStatus = TenantStatus.ACTIVE


class TenantCreate(Tenant):
    """Tenant model to create database record"""
    pass
    

class BankDetailsResponse(BankDetailsCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID


class TenantResponse(TenantCreate):
    """Tenant model to return from the endpoint"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Один объект вместо списка
    banking_details: Optional[BankDetailsResponse] = None


class BankDetailsRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    bank_name: str
    account_number: str
    bic: str
    corr_account: str | None = None
    kpp: str | None = None
    currency: str
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


class MembershipCreate(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str = "owner"