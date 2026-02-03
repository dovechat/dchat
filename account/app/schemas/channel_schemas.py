import uuid
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TelegramBotCredentials(BaseModel):
    """Credentials for Telegram Bot channel"""
    bot_token: str = Field(..., min_length=1, description="Telegram bot token from @BotFather")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for receiving updates")


class TelegramUserCredentials(BaseModel):
    """Credentials for Telegram User (phone number) channel"""
    phone: str = Field(..., min_length=10, description="Phone number with country code")
    # api_id: str = Field(..., description="Telegram API ID")
    # api_hash: str = Field(..., description="Telegram API hash")
    # session_string: Optional[str] = Field(None, description="Session string for authorized account")


class VKCredentials(BaseModel):
    """Credentials for VK channel"""
    access_token: str = Field(..., description="VK access token")
    group_id: Optional[str] = Field(None, description="VK group/community ID")


class ChannelAccountResponse(BaseModel):
    """Response with channel account info"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID
    channel_type: str  # from related Line
    phone: str | None = None
    state_json: Optional[dict] = None
    # !!! credentials_encrypted not exposed for security
    updated_at: Optional[str] = None


class ChannelAccountUpdate(BaseModel):
    """Generic update for state_json (without credentials)"""
    state_json: Optional[dict] = None