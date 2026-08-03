import uuid
import enum
from sqlalchemy import (
    Boolean,
    Column,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from models.tenants import User

class MessageDirection(enum.Enum):
    inbound = "inbound"
    outbound = "outbound"

class MessageStatus(enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    error = "error"

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="CASCADE"), nullable=False, index=True)
    line = relationship("Line", foreign_keys=[line_id])
    channel_type = Column(String, nullable=False)
    crm_chat_id = Column(String, index=True)
    client_phone = Column(String, index=True)
    is_closed = Column(Boolean, default=False, nullable=False, server_default="false")
    meta = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        Index("ix_conversations_line_id_channel_type", "line_id", "channel_type"),
    )

class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    user = relationship("User", foreign_keys=[user_id])
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_msg_id = Column(String, index=True)
    direction = Column(Enum(MessageDirection, native_enum=False), nullable=False, index=True)
    status = Column(Enum(MessageStatus, native_enum=False), default=MessageStatus.sent, index=True)
    text = Column(String)
    raw_content = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    media = relationship("Media", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

class MessageStatusEvent(Base):
    __tablename__ = "message_status_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(MessageStatus, native_enum=False), nullable=False, index=True)
    details = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)

class Media(Base):
    __tablename__ = "media"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
