import uuid
import enum
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from core.database import Base

class LineStatus(enum.Enum):
    active = "active"
    disabled = "disabled"
    expired = "expired"

class InstanceStatus(enum.Enum):
    idle = "idle"
    busy = "busy"
    maintenance = "maintenance"
    error = "error"

class PoolEventType(enum.Enum):
    allocate = "allocate"
    clean = "clean"
    release = "release"

class ConnectionStatus(enum.Enum):
    connected = "connected"
    disconnected = "disconnected"
    error = "error"
    blocked = "blocked"

class ChannelType(enum.Enum):
    telegram_user = "telegram_user"
    telegram_bot = "telegram_bot"
    whatsapp_green = "whatsapp_green"
    waba = "waba"

class Provider(enum.Enum):
    green = "green"
    waba = "waba"

from sqlalchemy import Column, Index, Integer, BigInteger, String, Text, JSON, Enum, ForeignKey, DateTime, Boolean, UniqueConstraint

class Line(Base):
    __tablename__ = "lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(Enum(LineStatus, native_enum=False), default=LineStatus.active, nullable=False, index=True)
    is_demo = Column(Boolean, default=False, index=True)
    connection_state = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_lines_tenant_id_status", "tenant_id", "status"),
    )


class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(Enum(ChannelType, native_enum=False), nullable=False, index=True)

    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    credentials_encrypted = Column(JSON, nullable=False)
    encryption_metadata = Column(JSON, server_default='{"v": 1}')
    state_json = Column(JSON)
    updated_at = Column(DateTime, onupdate=func.now())

    connection_status = Column(
        Enum(ConnectionStatus, native_enum=False),
        server_default='disconnected',
        default=ConnectionStatus.disconnected,
        nullable=False,
        index=True
    )

    connection_error = Column(String, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    session_string = Column(Text)
    bot_token = Column(String, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint('line_id', 'channel_type', name='uq_channel_account_line_channel'),
        Index("ix_channel_account_line_id_channel_type", "line_id", "channel_type"),
    )

class Instance(Base):
    __tablename__ = "instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(Enum(Provider, native_enum=False), default=Provider.green, nullable=False, index=True)
    external_id = Column(String, unique=True, index=True)
    token = Column(String, nullable=True, index=False)
    status = Column(Enum(InstanceStatus, native_enum=False), default=InstanceStatus.idle, nullable=False, index=True)
    last_cleanup_at = Column(DateTime)
    allocated_to_line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="SET NULL"), unique=True, index=True)
    version = Column(Integer, default=0, nullable=False)
    health = Column(JSON)

class InstancePoolEvent(Base):
    __tablename__ = "instance_pool_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    instance_id = Column(UUID(as_uuid=True), ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(Enum(PoolEventType, native_enum=False), nullable=False, index=True)
    details = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)