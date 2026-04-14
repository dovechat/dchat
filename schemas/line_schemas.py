import uuid
from datetime import datetime
from enum import Enum
from typing import  Optional
from pydantic import BaseModel, ConfigDict


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


class ChannelType(str, Enum):
    WHATSAPP_GREEN = "whatsapp_green"
    WABA = "waba"
    TELEGRAM_USER = "telegram_user"
    TELEGRAM_BOT = "telegram_bot"
    VK = "vk"