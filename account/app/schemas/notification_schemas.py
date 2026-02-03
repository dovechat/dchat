from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator
import re

from models.notifications import (
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)


# ============ NotificationSettings ============

class NotificationSettingsBase(BaseModel):
    notification_type: NotificationType
    channel: NotificationChannel
    enabled: bool = True
    target: str

    @field_validator('target')
    @classmethod
    def validate_target(cls, v: str, info) -> str:
        channel = info.data.get('channel')

        if channel == NotificationChannel.email:
            # Простая проверка email
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
                raise ValueError('Invalid email format')

        elif channel == NotificationChannel.telegram:
            # Telegram chat_id - число или @username
            if not (v.startswith('@') or v.lstrip('-').isdigit()):
                raise ValueError('Invalid telegram chat_id (must be @username or numeric)')

        elif channel == NotificationChannel.sms:
            # Телефон - только цифры и +
            if not re.match(r'^\+?[0-9]{10,15}$', v):
                raise ValueError('Invalid phone format (use +1234567890)')

        return v


class NotificationSettingsCreate(NotificationSettingsBase):
    pass


class NotificationSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    target: Optional[str] = None


class NotificationSettingsResponse(NotificationSettingsBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ NotificationLog ============

class NotificationLogResponse(BaseModel):
    id: int
    tenant_id: UUID
    notification_type: NotificationType
    channel: NotificationChannel
    target: str
    message: str
    status: NotificationStatus
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True