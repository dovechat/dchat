"""Bitrix24 install handler."""
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
import os

from app.core.dependencies import get_crm_service
from app.services.crm_service import CrmService

log = logging.getLogger("uvicorn.error")

install_router = APIRouter(prefix="/install", tags=["install"])
static_router = APIRouter(prefix="/html", tags=["html"])

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "html")


@install_router.api_route("/bitrix", methods=["GET", "POST"])
async def bitrix_placement():
    return FileResponse(os.path.join(HTML_DIR, "login.html"))

@static_router.api_route("/lines.html", methods=["GET", "POST"])
async def lines_placement():
    return FileResponse(os.path.join(HTML_DIR, "lines.html"))

@static_router.api_route("/success.html", methods=["GET", "POST"])
async def success_placement():
    return FileResponse(os.path.join(HTML_DIR, "success.html"))

@static_router.api_route("/login.html", methods=["GET", "POST"])
async def login_placement():
    return FileResponse(os.path.join(HTML_DIR, "login.html"))

@static_router.api_route("/install_finish.html", methods=["GET", "POST"])
async def install_finish():
    return FileResponse(os.path.join(HTML_DIR, "install_finish.html"))

@static_router.api_route("/html/contact-tab.html", methods=["GET", "POST"])
async def contact_tab():
    return FileResponse(os.path.join(HTML_DIR, "contact_tab.html"))


@install_router.post("/bitrix/onappinstall")
async def bitrix_onappinstall(
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    body = await request.body()
    domain = request.query_params.get("DOMAIN", "")
    return await crm_service.handle_onappinstall(body, domain=domain)


@install_router.post("/bitrix/auth")
async def bitrix_auth(
    body: dict,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.get_lines_for_bitrix(
        email=body["email"],
        password=body["password"],
        bx_auth=body.get("bx_auth", {}),
    )


@install_router.post("/bitrix/connect")
async def bitrix_connect(
    body: dict,
    crm_service: CrmService = Depends(get_crm_service),
):
    import uuid as _uuid
    return await crm_service.connect_line(
        line_id=_uuid.UUID(body["line_id"]),
        bx_auth=body.get("bx_auth", {}),
    )


@install_router.post("/bitrix/select-tenant")
async def bitrix_select_tenant(body: dict, crm_service: CrmService = Depends(get_crm_service)):
    return await crm_service.get_lines_for_tenant(
        jwt_token=body["jwt_token"],
        tenant_id=body["tenant_id"],
        bx_auth=body.get("bx_auth", {}),
    )