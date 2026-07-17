import uuid

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TelegramBotCredentials(BaseModel):
    """Credentials for Telegram Bot channel"""
    bot_token: str = Field(..., min_length=1, description="Telegram bot token from @BotFather")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for receiving updates")
    secret_token: Optional[str] = Field(None, description="Webhook secret")


class TelegramUserCredentials(BaseModel):
    """Credentials for Telegram User (phone number) channel"""
    phone: str = Field(None, description="Phone number with country code")
    # api_id: str = Field(..., description="Telegram API ID")
    # api_hash: str = Field(..., description="Telegram API hash")
    session_string: Optional[str] = Field(None, description="Session string for authorized account")


class VKCredentials(BaseModel):
    """Credentials for VK channel"""
    access_token: str = Field(..., description="VK access token")
    group_id: Optional[str] = Field(None, description="VK group/community ID")
    secret_key: Optional[str] = Field(None, description="VK callback secret key")
    confirmation_code: Optional[str] = Field(None, description="VK confirmation code")

class VKOAuthStartResponse(BaseModel):
    authorize_url: str


class VKGroupOption(BaseModel):
    id: int
    name: str
    screen_name: str
    photo_100: str | None = None


class VKOAuthCallbackResult(BaseModel):
    payload: str
    groups: list[VKGroupOption]


class VKOAuthConfirmRequest(BaseModel):
    payload: str
    group_id: int


class ChannelAccountResponse(BaseModel):
    """Response with channel account info"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None
    line_id: uuid.UUID
    channel_type: str  # from related Line
    phone: str | None = None
    state_json: Optional[dict] = None
    # !!! credentials_encrypted not exposed for security
    expires_at: datetime | None = None
    updated_at: datetime | None = None
    connection_status: str | None = None
    amo_connected: bool = False


class ChannelAccountUpdate(BaseModel):
    """Generic update for state_json (without credentials)"""
    state_json: Optional[dict] = None


class CreateWhatsAppGreenSchema(BaseModel):
    id_instance: str | None = None
    api_token: str | None = None


class CreateWabaSchema(BaseModel):
    api_key: str