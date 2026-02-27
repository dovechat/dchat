import uuid
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer
from core.dependencies import get_current_user, get_line_service
from schemas.line_schemas import LineResponse

from services.line_service import LineService
from schemas.auth_schemas import UserContext
import logging

log = logging.getLogger("uvicorn.error")
auth_scheme = HTTPBearer()

line_router = APIRouter(
    tags=["Lines"], 
    prefix="/tenants/{tenant_id}/lines",
    dependencies=[Depends(auth_scheme)]
)

def check_tenant_access(tenant_id: uuid.UUID, current_user: UserContext = Depends(get_current_user)):
    if current_user.tenant_id != tenant_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Token tenant_id mismatch")
    return tenant_id

@line_router.get("/{line_id}", response_model=LineResponse)
async def get_line(
    line_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    line_service: LineService = Depends(get_line_service)
) -> LineResponse:
    return await line_service.get_line(line_id, tenant_id)