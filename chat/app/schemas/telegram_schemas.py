import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"

class KafkaEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    account_phone: str  # Номер телефона аккаунта Telegram
    payload: dict = {}

class IncomingMessageEvent(KafkaEvent):
    """Событие входящего сообщения"""
    chat_id: int  # Telegram chat_id
    message_id: int  # Telegram message_id
    sender_id: Optional[int]  # Telegram user_id отправителя
    text: Optional[str]
    media_info: Optional[Dict[str, Any]] = None
    raw_update: Dict[str, Any]  # Оригинальный update от TDLib

class MessageStatusEvent(KafkaEvent):
    """Событие изменения статуса сообщения"""
    chat_id: int
    message_id: int
    status: str  # sent, delivered, read, error
    error_details: Optional[str] = None

class ContactSyncEvent(KafkaEvent):
    """Событие синхронизации контакта"""
    chat_id: int
    chat_type: str  # private, group, channel, etc
    title: str
    username: Optional[str] = None
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_contact: bool = False

class SendMessageRequest(BaseModel):
    session_string: str | None = None
    phone_number: str | None = None # Телефон отправителя (чья session)
    recipient: int | str  # Кому отправить (username или phone)
    message: str


class TelegramOutgoingMessage(BaseModel):
    user_id: str  # ID пользователя в вашей системе
    session_string: str
    recipient: str | int
    message: str










