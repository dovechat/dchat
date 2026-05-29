"""Webhooks from CRM systems."""
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