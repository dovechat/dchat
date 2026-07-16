import httpx
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from core.config import settings
from app.schemas.vk_oauth_schemas import VKOAuthStartResponse, VKOAuthConfirmRequest
from app.services.vk_oauth_service import VKOAuthService
from app.services.channel_service import ChannelAccountService
from app.core.dependencies import get_channel_account_repo, get_channel_service, get_line_repo
from app.schemas.channel_schemas import ChannelAccountResponse

import logging
logging.getLogger('uvicorn.error').setLevel(logging.DEBUG)
log = logging.getLogger(__name__)

vk_oauth_router = APIRouter(prefix="/tenants/{tenant_id}/lines/{line_id}/account/vk/oauth", tags=["vk_oauth"])

log.info("---------------------------- vk_oauth_router")

def get_vk_oauth_service(
    channel_repo=Depends(get_channel_account_repo),
    line_repo=Depends(get_line_repo),
) -> VKOAuthService:
    return VKOAuthService(channel_repo, line_repo)


@vk_oauth_router.get("/start", response_model=VKOAuthStartResponse)
async def vk_oauth_start(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    service: VKOAuthService = Depends(get_vk_oauth_service),
) -> VKOAuthStartResponse:
    url = service.build_authorize_url(tenant_id, line_id)
    return VKOAuthStartResponse(authorize_url=url)


@vk_oauth_router.get("/callback")
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


@vk_oauth_router.post("/confirm")
async def vk_oauth_confirm(
    body: VKOAuthConfirmRequest,
    service: VKOAuthService = Depends(get_vk_oauth_service),
):
    return await service.confirm_group(body.payload, body.group_id)


@vk_oauth_router.post("/mock-connect")
async def vk_oauth_mock_connect(
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    channel_service: ChannelAccountService = Depends(get_channel_service),
) -> ChannelAccountResponse:
    access_token = settings.VK_TEMP_TOKEN
    group_id = settings.VK_TEMP_GROUP_ID

    async with httpx.AsyncClient() as client:
        server_id = await channel_service._vk_add_callback_server(
            client, group_id, access_token, settings.VK_TEMP_SECRET_KEY or "", line_id
        )
        await channel_service._vk_set_callback_settings(client, group_id, server_id, access_token)

    creds_dict = {
        "access_token": access_token,
        "group_id": group_id,
        "server_id": server_id,
        "confirmation_code": settings.VK_TEMP_CONFIRMATION_CODE,
        "secret_key": settings.VK_TEMP_SECRET_KEY,
    }
    encrypted = channel_service._encrypt_credentials(creds_dict)
    account = await channel_service.channel_repo.get_by_line_and_type(line_id, "vk")

    if account:
        updated = await channel_service.channel_repo.update_account(account, credentials_encrypted=encrypted)
    else:
        updated = await channel_service.channel_repo.create_account(line_id=line_id, credentials_encrypted=encrypted)

    return ChannelAccountResponse(
        id=updated.id,
        line_id=updated.line_id,
        channel_type=updated.channel_type,
        state_json=updated.state_json,
        updated_at=updated.updated_at.isoformat() if updated.updated_at else None
    )