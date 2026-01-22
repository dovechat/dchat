import uuid
import enum
from sqlalchemy import Column, Index, BigInteger, String, JSON, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from core.database import Base

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
    crm_type = Column(String, nullable=False)
    crm_chat_id = Column(String, index=True)
    client_phone = Column(String, index=True)
    meta = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, onupdate=func.now())

class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_msg_id = Column(String, index=True)
    direction = Column(Enum(MessageDirection, native_enum=False), nullable=False, index=True)
    status = Column(Enum(MessageStatus, native_enum=False), default=MessageStatus.sent, index=True)
    text = Column(String)
    media_id = Column(String)
    raw_content = Column(JSON)
    created_at = Column(DateTime, server_default=func.now(), index=True)

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