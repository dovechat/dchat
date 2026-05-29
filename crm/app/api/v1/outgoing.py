"""Outgoing CRM messages."""
import os
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from crm.app.core.uow import CrmUnitOfWork
from crm.app.services.crm_service import CrmService
import logging
log = logging.getLogger("uvicorn.error")

outgoing_router = APIRouter(prefix="/outgoing", tags=["outgoing"])

def get_uow(db: AsyncSession = Depends(get_db)) -> CrmUnitOfWork:
    return CrmUnitOfWork(db)

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "html")

@outgoing_router.get("/lines")
async def get_lines_for_member(member_id: str, uow: CrmUnitOfWork = Depends(get_uow)):
    service = CrmService(uow)
    return await service.get_lines_for_member(member_id)


@outgoing_router.post("/start")
async def start_outgoing(body: dict, uow: CrmUnitOfWork = Depends(get_uow)):
    service = CrmService(uow)
    return await service.start_outgoing(
        member_id=body.get("member_id"),
        contact_id=body.get("contact_id"),
        line_id=uuid.UUID(body.get("line_id")),
        channel_account_id=uuid.UUID(body.get("channel_account_id")) if body.get("channel_account_id") else None,
        text=body.get("text", ""),
    )

@outgoing_router.api_route("/contact-tab", methods=["GET", "POST"])
async def contact_tab():
    return FileResponse(os.path.join(HTML_DIR, "contact_tab.html"))

