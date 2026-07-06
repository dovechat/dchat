"""CRM connection management — ЛК."""
import uuid
from fastapi import APIRouter, Depends
from app.core.dependencies import get_crm_service
from app.services.crm_service import CrmService
from app.schemas.crm_schemas import CrmConnectRequest, CrmConnectionResponse, AmoAccountOut, AmoLineConnectRequest

connections_router = APIRouter(prefix="/connections", tags=["connections"])


@connections_router.post("/{tenant_id}", response_model=CrmConnectionResponse)
async def connect_crm(
    tenant_id: uuid.UUID,
    body: CrmConnectRequest,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.connect(tenant_id, body)


@connections_router.delete("/{tenant_id}/{crm_type}")
async def disconnect_crm(
    tenant_id: uuid.UUID,
    crm_type: str,
    crm_service: CrmService = Depends(get_crm_service),
):
    await crm_service.disconnect(tenant_id, crm_type)
    return {"status": "ok"}


# AMO ------

@connections_router.post("/amo/{tenant_id}/connect-channel")
async def amo_connect_channel(
    tenant_id: uuid.UUID,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.amo_connect_channel(tenant_id)

@connections_router.get("/amo", response_model=list[AmoAccountOut])
async def list_amo_accounts(
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.list_amo_accounts()


@connections_router.post("/amo/line")
async def connect_amo_line(
    body: AmoLineConnectRequest,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.connect_amo_line(body)


@connections_router.get("/{tenant_id}", response_model=list[CrmConnectionResponse])
async def get_connections(
    tenant_id: uuid.UUID,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.get_connections(tenant_id)


@connections_router.delete("/amo/line/{line_id}")
async def disconnect_amo_line(
    line_id: uuid.UUID,
    crm_service: CrmService = Depends(get_crm_service),
):
    await crm_service.disconnect_amo_line(line_id)
    return {"status": "ok"}