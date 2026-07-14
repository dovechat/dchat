"""Bitrix24 install handler."""
import logging
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
import os

from app.core.dependencies import get_crm_service
from app.services.crm_service import CrmService
from crm.app.schemas.crm_schemas import AmoSaveTokensRequest

log = logging.getLogger("uvicorn.error")

install_router = APIRouter(prefix="/install", tags=["install"])
static_router = APIRouter(prefix="/html", tags=["html"])

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "html")
templates = Jinja2Templates(directory=HTML_DIR)

@install_router.get("/bitrix")
async def bitrix_placement_get(request: Request):
    from core.config import settings
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "host_url": settings.host_url},
    )

@install_router.post("/bitrix")
async def bitrix_placement_post(
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    body = await request.body()
    domain = request.query_params.get("DOMAIN", "")
    return await crm_service.handle_onappinstall(body, domain=domain)

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

# AMO ---------

@install_router.get("/amo")
async def amo_install_redirect():
    from core.config import settings
    from fastapi.responses import RedirectResponse
    params = (
        f"client_id={settings.AMO_CLIENT_ID}"
        f"&redirect_uri={settings.AMO_REDIRECT_URI}"
        f"&response_type=code"
        f"&state=install"
        f"&mode=popup"
    )
    return RedirectResponse(f"https://www.kommo.com/oauth?{params}")


@install_router.get("/amo/callback")
async def amo_oauth_callback(
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    code = request.query_params.get("code")
    log.info(f"amo_oauth_callback params={dict(request.query_params)}")
    referer = request.query_params.get("referer", "")
    domain = referer.replace("https://", "").replace("http://", "").rstrip("/")
    return await crm_service.handle_amo_install(code=code, domain=domain)


@install_router.get("/amo/auth-url")
async def amo_auth_url():
    from core.config import settings
    from fastapi.responses import JSONResponse
    params = (
        f"client_id={settings.AMO_CLIENT_ID}"
        f"&redirect_uri={settings.AMO_REDIRECT_URI}"
        f"&response_type=code"
        f"&state=install"
    )
    return JSONResponse({"url": f"https://new1782329019.amocrm.ru/oauth2/authorize?{params}"})



@install_router.post("/amo/save-tokens")
async def amo_save_tokens(
    body: AmoSaveTokensRequest,
    crm_service: CrmService = Depends(get_crm_service),
):
    from core.config import settings
    from infra.crypto import encrypt
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"https://{body.domain}/api/v4/account?with=amojo_id",
            headers={"Authorization": f"Bearer {body.access_token}"},
        )
        resp.raise_for_status()
        account = resp.json()
        log.info(f"amo_save_tokens account response={account}")
    account_id = str(account["id"])
    amojo_id = account.get("amojo_id", "")
    await crm_service._uow.crm_connections.upsert_amo(
        domain=body.domain,
        account_id=account_id,
        amojo_id=amojo_id,
        access_token_enc=encrypt(body.access_token),
        refresh_token_enc=encrypt(body.refresh_token),
        tenant_id=body.tenant_id,
    )
    log.info(f"amo_save_tokens saved domain={body.domain} account_id={account_id}")
    return {"ok": True, "account_id": account_id, "amojo_id": amojo_id}
