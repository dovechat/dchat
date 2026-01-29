import uuid
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer
from core.dependencies import get_current_user
from app.core.dependencies import check_tenant_access, get_channel_service
from app.schemas.channel_schemas import (
    TelegramBotCredentials,
    TelegramUserCredentials,
    VKCredentials,
    ChannelAccountResponse,
    ChannelAccountUpdate
)
from app.services.channel_service import ChannelAccountService
from schemas.auth_schemas import UserContext
import logging

log = logging.getLogger("uvicorn.error")
auth_scheme = HTTPBearer()

channel_router = APIRouter(
    tags=["Channels"],
    prefix="/tenants/{tenant_id}/lines/{line_id}/account",
    dependencies=[Depends(auth_scheme)]
)


@channel_router.get("/", response_model=ChannelAccountResponse)
async def get_channel_account(
        line_id: uuid.UUID,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> ChannelAccountResponse:
    """Get channel account info (without decrypted credentials)"""
    return await channel_service.get_account(line_id, tenant_id)


@channel_router.patch("/telegram-bot", response_model=ChannelAccountResponse)
async def update_telegram_bot_credentials(
        line_id: uuid.UUID,
        credentials: TelegramBotCredentials,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> ChannelAccountResponse:
    """Update Telegram Bot credentials"""
    return await channel_service.update_telegram_bot(line_id, tenant_id, credentials)


@channel_router.patch("/telegram-user", response_model=ChannelAccountResponse)
async def update_telegram_user_credentials(
        line_id: uuid.UUID,
        credentials: TelegramUserCredentials,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> ChannelAccountResponse:
    """Update Telegram User credentials"""
    return await channel_service.update_telegram_user(line_id, tenant_id, credentials)


@channel_router.patch("/vk", response_model=ChannelAccountResponse)
async def update_vk_credentials(
        line_id: uuid.UUID,
        credentials: VKCredentials,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> ChannelAccountResponse:
    """Update VK credentials"""
    return await channel_service.update_vk(line_id, tenant_id, credentials)

'''
Needs to move to connector service, it's shouldn't belong to account service 
@channel_router.patch("/state", response_model=ChannelAccountResponse)
async def update_channel_state(
        line_id: uuid.UUID,
        data: ChannelAccountUpdate,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> ChannelAccountResponse:
    """Update channel state (connection status, etc.)"""
    if data.state_json is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="state_json is required")

    return await channel_service.update_state(line_id, tenant_id, data.state_json)
'''