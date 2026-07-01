import enum
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, model_validator
from models.messages import MessageDirection, MessageStatus

class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    error = "error"

class ConversationCreate(BaseModel):
    line_id: uuid.UUID
    channel_type: str
    crm_chat_id: str | None = None
    client_phone: str | None = None
    meta: dict | None = None
    

class MessageCreate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    message_id: int | None = None
    conversation_id: uuid.UUID
    channel_msg_id: str | None = None
    direction: MessageDirection
    phone: str | None = None
    text: str | None = None
    media: list[dict] | None = None  # [{"file_name": ..., "mime_type": ...}]
    raw_content: dict | None = None
    status: MessageStatus = "sent"
    template: dict | None = None  # {"name": ..., "language": ..., "components": [...]}

    @model_validator(mode="after")
    def check_template_or_media(self) -> "MessageCreate":
        if self.template and self.media:
            raise ValueError("template и media не могут быть заданы одновременно")
        return self


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
    channel_type: str
    crm_chat_id: str | None = None
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
    channel_type: str
    crm_chat_id: str | None = None
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


# ------ VK ------

class VkMessage(BaseModel):
    id: int
    date: int
    peer_id: int
    from_id: int
    text: str


class VkObject(BaseModel):
    message: VkMessage


class VkWebhook(BaseModel):
    type: str
    group_id: int
    secret: str
    object: VkObject


class CrmMessageIn(BaseModel):
    line_id: uuid.UUID
    crm_chat_id: str
    channel_type: str
    text: str
    raw_content: dict = {}
    media: list[dict] = []
    user_id: uuid.UUID
    user_email: str

class CrmMessageOut(BaseModel):
    line_id: uuid.UUID
    client_phone: str
    text: str
    crm_connection_id: uuid.UUID
    contact_id: str
    crm_line_id: str
    connector_id: str
    channel_type: str
    channel_account_id: uuid.UUID | None
    media: list[dict] = []