import uuid
import enum
from sqlalchemy import Column, Index, Integer, BigInteger, String, JSON, Enum, ForeignKey, DateTime, Boolean
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

class Line(Base):
    __tablename__ = "lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    channel_type = Column(String, nullable=False, index=True)
    status = Column(Enum(LineStatus, native_enum=False), default=LineStatus.active, nullable=False, index=True)
    is_demo = Column(Boolean, default=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    connection_state = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)

class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    credentials_encrypted = Column(JSON, nullable=False)
    encryption_metadata = Column(JSON, server_default='{"v": 1}')
    state_json = Column(JSON)
    updated_at = Column(DateTime, onupdate=func.now())
    connection_status = Column(
        Enum(ConnectionStatus, native_enum=False),
        server_default='disconnected',  # ⬅️ добавить
        default=ConnectionStatus.disconnected,
        nullable=False,
        index=True
    )
    connection_error = Column(String, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

class Instance(Base):
    __tablename__ = "instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String, nullable=False, index=True)
    external_id = Column(String, unique=True, index=True)
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