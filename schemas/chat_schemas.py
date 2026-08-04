import enum
import uuid
from pydantic import BaseModel, Field
from models.messages import MessageDirection

class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    error = "error"

class MessageCreate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    message_id: int | None = None
    conversation_id: uuid.UUID
    channel_msg_id: str | None = None
    crm_message_id: str | None = None
    direction: MessageDirection
    phone: str | None = None
    text: str | None = None
    media: list[dict] | None = None  # [{"file_name": ..., "mime_type": ...}]
    raw_content: dict | None = None
    status: MessageStatus = "sent" 