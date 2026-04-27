import enum
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from models.messages import MessageDirection, MessageStatus

class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    error = "error"

class ConversationCreate(BaseModel):
    line_id: uuid.UUID
    crm_type: str
    crm_chat_id: str
    client_phone: str | None = None
    meta: dict | None = None


class MessageCreate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    conversation_id: uuid.UUID
    channel_msg_id: str | None = None
    direction: MessageDirection
    phone: str | None = None
    text: str | None = None
    media: list[dict] | None = None  # [{"file_name": ..., "mime_type": ...}]
    raw_content: dict | None = None
    status: MessageStatus = "sent"


class MediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    file_name: str | None = None
    mime_type: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: uuid.UUID
    channel_msg_id: str | None = None
    direction: MessageDirection
    status: MessageStatus
    text: str | None = None
    raw_content: dict | None = None
    created_at: datetime
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    user_full_name: str | None = None
    media: list[MediaResponse] = []


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID
    line_name: str | None = None
    tenant_id: uuid.UUID | None = None  # добавить
    crm_type: str
    crm_chat_id: str
    client_phone: str | None = None
    meta: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None
    unread_count: int = 0
    last_message: MessageResponse | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID
    crm_type: str
    crm_chat_id: str
    client_phone: str | None = None
    meta: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None
    messages: List[MessageResponse] = []
    my_phone: str | None = None
    is_closed: bool = False


class LineResponse(BaseModel):
    id: uuid.UUID
    name: str
    channel_type: str | None = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ChannelAvailable(BaseModel):
    channel_type: str


class LineWithChannelsResponse(BaseModel):
    id: uuid.UUID
    name: str
    tenant_id: uuid.UUID
    tenant_name: str
    channels: list[ChannelAvailable]


class ConversationCloseRequest(BaseModel):
    is_closed: bool
