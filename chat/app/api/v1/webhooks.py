
import uuid
from fastapi import APIRouter, Request, Depends
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
    await green_listener.handle_webhook(line_id, payload)
    return {"status": "ok"}


@router.post("/whatsapp/waba/{line_id}")
async def waba_webhook(line_id: str, request: Request):
    waba_listener = request.app.state.waba_listener
    payload = await request.json()
    await waba_listener.handle_webhook(line_id, payload)
    return {"status": "ok"}
