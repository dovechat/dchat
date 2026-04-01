import uuid
import enum
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Enum,
    ForeignKey,
    DateTime,
    Boolean,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from core.database import Base


class NotificationType(enum.Enum):
    line_expiration = "line_expiration"
    line_connection_error = "line_connection_error"
    line_blocked = "line_blocked"
    low_balance = "low_balance"
    payment_success = "payment_success"


class NotificationChannel(enum.Enum):
    email = "email"
    telegram = "telegram"
    sms = "sms"
    internal = "internal"


class NotificationStatus(enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    notification_type = Column(Enum(NotificationType, native_enum=False), nullable=False, index=True)
    channel = Column(Enum(NotificationChannel, native_enum=False), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    target = Column(String, nullable=False)  # email / telegram_chat_id / phone

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "notification_type", "channel", name="uq_tenant_notification_channel"),
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    notification_type = Column(Enum(NotificationType, native_enum=False), nullable=False, index=True)
    channel = Column(Enum(NotificationChannel, native_enum=False), nullable=False)
    target = Column(String, nullable=False)

    message = Column(Text, nullable=False)
    status = Column(Enum(NotificationStatus, native_enum=False), default=NotificationStatus.pending, nullable=False,
                    index=True)
    error_message = Column(Text, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)