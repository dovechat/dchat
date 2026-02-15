import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from models.messages import MessageDirection, MessageStatus



class ConversationCreate(BaseModel):
    line_id: uuid.UUID
    crm_type: str
    crm_chat_id: str
    client_phone: Optional[str] = None
    meta: Optional[dict] = None


class MessageCreate(BaseModel):
    conversation_id: uuid.UUID
    channel_msg_id: Optional[str] = None
    direction: MessageDirection
    phone: Optional[str] = None
    text: Optional[str] = None
    media_id: Optional[str] = None
    raw_content: Optional[dict] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: uuid.UUID
    channel_msg_id: Optional[str] = None
    direction: MessageDirection
    status: MessageStatus
    text: Optional[str] = None
    media_id: Optional[str] = None
    raw_content: Optional[dict] = None
    created_at: datetime


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID
    crm_type: str
    crm_chat_id: str
    client_phone: Optional[str] = None
    meta: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    unread_count: int = 0
    last_message: Optional[MessageResponse] = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID
    crm_type: str
    crm_chat_id: str
    client_phone: Optional[str] = None
    meta: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[MessageResponse] = []
    my_phone: Optional[str] = None


