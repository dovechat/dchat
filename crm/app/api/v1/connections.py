"""CRM connection management — ЛК."""
import uuid
from fastapi import APIRouter, Depends
from app.core.dependencies import get_crm_service
from app.services.crm_service import CrmService
from app.schemas.crm_schemas import CrmConnectRequest, CrmConnectionResponse

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


@connections_router.get("/{tenant_id}", response_model=list[CrmConnectionResponse])
async def get_connections(
    tenant_id: uuid.UUID,
    crm_service: CrmService = Depends(get_crm_service),
):
    return await crm_service.get_connections(tenant_id)
