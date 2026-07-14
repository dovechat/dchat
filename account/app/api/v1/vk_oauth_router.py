import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.schemas.vk_oauth_schemas import VKOAuthStartResponse, VKOAuthConfirmRequest
from app.services.vk_oauth_service import VKOAuthService
from app.core.dependencies import get_channel_account_repo, get_line_repo

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