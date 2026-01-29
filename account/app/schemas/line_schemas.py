import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ChannelType(str, Enum):
    WHATSAPP_QR = "whatsapp_qr"
    WHATSAPP_BUSINESS = "whatsapp_business"
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"
    VK = "vk"


class LineStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class ConnectionState(str, Enum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    BLOCKED = "blocked"
    ERROR = "error"


class SubscriptionPeriod(str, Enum):
    MONTH = "month"
    YEAR = "year"


class LineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    channel_type: ChannelType
    subscription_period: SubscriptionPeriod = SubscriptionPeriod.MONTH
    is_demo: bool = False


class LineUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[LineStatus] = None


class LineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    channel_type: str
    status: str
    is_demo: bool
    expires_at: Optional[datetime] = None
    connection_state: Optional[dict] = None
    created_at: datetime


class LineListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    channel_type: str
    status: str
    is_demo: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    days_until_expiry: Optional[int] = None
    connection_status: str = "not_connected"