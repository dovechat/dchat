import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from app.core.dependencies import get_webhook_service
from app.services.webhook_service import WebhookService
import logging

log = logging.getLogger("uvicorn.error")

router = APIRouter(
    tags=["Webhooks"],
    prefix="/webhooks"
)


@router.post("/whatsapp/green/{line_id}")
async def whatsapp_green_webhook(
    line_id: uuid.UUID,
    request: Request,
    service: WebhookService = Depends(get_webhook_service)
):
    """Receive webhook from Green API for WhatsApp line"""
    body = await request.json()
    log.info(f"Green webhook for line {line_id}: {body.get('typeWebhook')}")
    await service.process_green_webhook(line_id, body)
    return {"status": "ok"}

@router.post("/vk/{line_id}")
async def whatsapp_vk_webhook(
    line_id: uuid.UUID,
    request: Request,
    service: WebhookService = Depends(get_webhook_service)
):
    """Receive webhook from Green API for WhatsApp line"""
    body = await request.json()
    log.info(f"Green webhook for line {line_id}: {body.get('typeWebhook')}")
    result = await service.process_vk_webhook(line_id, body)
    return PlainTextResponse(result)