"""Bitrix24 bizproc robot webhook handlers."""
import logging
import time
import uuid
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_crm_service
from app.services.crm_service import CrmService

log = logging.getLogger("uvicorn.error")

robots_router = APIRouter(prefix="/robots", tags=["robots"])


@robots_router.post("/{robot_code}")
async def robot_webhook(
    robot_code: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
):
    body = await request.body()
    parsed = parse_qs(body.decode())
    data = {k: v[0] for k, v in parsed.items()}
    log.info(f"robot_webhook raw data: {data}")
    return await crm_service.handle_robot(robot_code, data)