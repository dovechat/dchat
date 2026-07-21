
import uuid
from fastapi import APIRouter, Header, Request, Depends
from fastapi.responses import PlainTextResponse
from app.services.webhook_service import WebhookService
from app.core.dependencies import get_webhook_service

import logging
log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/whatsapp/green/{line_id}")
async def whatsapp_green_webhook(
    request: Request,
    line_id: uuid.UUID,
    service: WebhookService = Depends(get_webhook_service)
):
    payload = await request.json()
    log.info(f'@router.post(/whatsapp/green/{line_id} payload {payload}')
    green_listener = request.app.state.green_listener
    auth_header = request.headers.get("authorization")
    await green_listener.handle_webhook(line_id, payload, auth_header)
    return {"status": "ok"}


@router.post("/whatsapp/waba/{line_id}/{token}")
async def waba_webhook(line_id: str, token: str, request: Request):
    waba_listener = request.app.state.waba_listener
    payload = await request.json()
    await waba_listener.handle_webhook(line_id, token, payload)
    return {"status": "ok"}


@router.post("/vk/{line_id}")
async def vk_webhook(
    line_id: uuid.UUID,
    request: Request,
    service: WebhookService = Depends(get_webhook_service)
):
    """Receive webhook from Green API for WhatsApp line"""
    payload = await request.json()
    log.info(f"VK webhook for line {line_id}: {payload.get('type')}")
    vk_listener = request.app.state.vk_listener
    log.info(f"VK vk_listener {vk_listener}")
    result = await vk_listener.handle_webhook(line_id, payload)
    # result = await service.process_vk_webhook(line_id, payload)
    return PlainTextResponse(result)