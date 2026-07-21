import uuid
from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPBearer
from core.dependencies import get_current_user
from app.core.dependencies import (
    check_tenant_access,
    get_channel_account_repo,
    get_channel_service,
    get_cleanup_service,
    get_line_repo,
)
from services.cleanup_service import CleanupService
from app.schemas.channel_schemas import (
    TelegramBotCredentials,
    TelegramUserCredentials,
    VKCredentials,
    VKOAuthStartResponse,
    VKOAuthConfirmRequest,
    ChannelAccountResponse,
    ChannelAccountUpdate,
    CreateWabaSchema,
    CreateWhatsAppGreenSchema
)
from app.schemas.line_schemas import ChannelType
from app.services.channel_service import ChannelAccountService
from app.services.vk_oauth_service import VKOAuthService
from schemas.auth_schemas import UserContext
import logging

log = logging.getLogger("uvicorn.error")
auth_scheme = HTTPBearer()

channel_router = APIRouter(
    tags=["Channels"],
    prefix="/tenants/{tenant_id}/lines/{line_id}/account",
    dependencies=[Depends(auth_scheme)]
)


def get_vk_oauth_service(
    channel_repo=Depends(get_channel_account_repo),
    line_repo=Depends(get_line_repo),
) -> VKOAuthService:
    return VKOAuthService(channel_repo, line_repo)



@channel_router.get("/start", response_model=VKOAuthStartResponse)
async def vk_oauth_start(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    service: VKOAuthService = Depends(get_vk_oauth_service),
) -> VKOAuthStartResponse:
    url = service.build_authorize_url(tenant_id, line_id)
    return VKOAuthStartResponse(authorize_url=url)




@channel_router.get("/callback")
async def vk_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    service: VKOAuthService = Depends(get_vk_oauth_service),
):
    if error or not code or not state:
        return RedirectResponse(f"https://tg.dove-chat.pro/dev/lc/vk-oauth-result?error={error or 'no_code'}")

    try:
        payload, groups = await service.handle_callback(code, state)
    except Exception as e:
        return RedirectResponse(f"https://tg.dove-chat.pro/dev/lc/vk-oauth-result?error={type(e).__name__}")

    groups_json = "&".join(f"g={g.id}:{g.name}" for g in groups)
    return RedirectResponse(
        f"https://tg.dove-chat.pro/dev/lc/vk-oauth-result?payload={payload}&{groups_json}"
    )


@channel_router.post("/confirm")
async def vk_oauth_confirm(
    body: VKOAuthConfirmRequest,
    service: VKOAuthService = Depends(get_vk_oauth_service),
):
    return await service.confirm_group(body.payload, body.group_id)


@channel_router.get("/", response_model=list[ChannelAccountResponse])
async def get_channel_accounts(
        line_id: uuid.UUID,
        current_user: UserContext = Depends(get_current_user),
        tenant_id: uuid.UUID = Depends(check_tenant_access),
        channel_service: ChannelAccountService = Depends(get_channel_service)
) -> list[ChannelAccountResponse]:
    return await channel_service.get_accounts(line_id, tenant_id)


@channel_router.patch("/toggle/{channel_type}")
async def update_account(
    line_id: uuid.UUID,
    channel_type: ChannelType,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    channel_service: ChannelAccountService = Depends(get_channel_service)
):
    return await channel_service.update_account(line_id, tenant_id, channel_type)


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

@channel_router.post("/whatsapp-green")
async def configure_whatsapp_green(
    line_id: uuid.UUID,
    data: CreateWhatsAppGreenSchema,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: ChannelAccountService = Depends(get_channel_service)
):
    res = await service.update_whatsapp_green(line_id, tenant_id, data.id_instance, data.api_token)
    log.info(f"channel_router configure_whatsapp_green res {res}")
    return {"status": "ok", "line_id": res.line_id}


@channel_router.post("/whatsapp-green/qr")
async def get_whatsapp_qr(
    line_id: uuid.UUID,
    data: CreateWhatsAppGreenSchema,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    service: ChannelAccountService = Depends(get_channel_service)
):
    """Получить QR-код от Green API"""
    qr_data = await service.get_qr_from_green(data.id_instance, data.api_token)
    return {"qr": qr_data}


@channel_router.post("/whatsapp-green/connect")
async def connect_whatsapp_green(
    line_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: ChannelAccountService = Depends(get_channel_service)
):
    qr_data = await service.connect_whatsapp_green(line_id, tenant_id)
    return {"qr": qr_data}


@channel_router.post("/waba")
async def configure_waba(
    line_id: uuid.UUID,
    data: CreateWabaSchema,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: ChannelAccountService = Depends(get_channel_service)
):
    log.info(f"channel_router configure_waba data {data}")
    res = await service.update_waba(line_id, tenant_id, data.api_key)
    log.info(f"channel_router configure_waba res {res}")
    return {"status": "ok", "line_id": res.line_id}


@channel_router.post("/cleanup")
async def cleanup_line(
    line_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    cleanup_service: CleanupService = Depends(get_cleanup_service),
    channel_service: ChannelAccountService = Depends(get_channel_service),
):
    accounts = await channel_service.get_accounts(line_id, tenant_id)
    for account in accounts:
        await cleanup_service.cleanup_line(line_id, channel_type=account.channel_type)
    return {"status": "ok"}


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