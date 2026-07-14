"""Webhooks from CRM systems."""
import json
import uuid
from fastapi import APIRouter, Depends, Request
from app.core.dependencies import get_uow
from app.core.dependencies import get_crm_service
from app.core.uow import CrmUnitOfWork
from app.services.crm_service import CrmService

import logging
log = logging.getLogger("uvicorn.error")

webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@webhooks_router.post("/{crm_type}")
async def crm_webhook(
        crm_type: str,
        request: Request,
        uow: CrmUnitOfWork = Depends(get_uow),
):
    body = await request.body()
    log.info(f"BITRIX RAW BODY: {body}")
    from urllib.parse import parse_qs
    parsed = parse_qs(body.decode())
    data = {k: v[0] for k, v in parsed.items()}
    log.info(f"BITRIX WEBHOOK: {data}")

    crm_service = CrmService(uow)
    await crm_service.handle_bitrix_incoming(data)

    return {"status": "ok"}


@webhooks_router.api_route("/install/bitrix", methods=["GET", "POST"])
async def bitrix_install():
    from fastapi.responses import HTMLResponse
    html = """<html>
<head><script src="//api.bitrix24.com/api/v1/"></script></head>
<body><script>BX24.init(function(){ BX24.installFinish(); });</script></body>
</html>"""
    return HTMLResponse(content=html)


@webhooks_router.post("/bitrix/check-wa-tg")
async def bitrix_check_wa_tg(
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    body = await request.body()
    from urllib.parse import parse_qs
    parsed = parse_qs(body.decode())
    data = {k: v[0] for k, v in parsed.items()}
    log.info(f"bitrix_check_wa_tg data: {data}")
    return await crm_service.check_wa_tg(data)

# AMO ------

@webhooks_router.post("/amo/{amojo_id}")
async def amo_webhook(
    amojo_id: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    # amojo_id может прийти как scope_id (channel_id_amojo_id)
    if "_" in amojo_id:
        amojo_id = amojo_id.split("_", 1)[1]
    await crm_service.handle_amo_incoming(body, amojo_id=amojo_id, signature=signature)
    return {"status": "ok"}