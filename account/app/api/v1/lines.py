import uuid
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer
from core.dependencies import get_current_user
from app.core.dependencies import get_line_service
from app.schemas.line_schemas import (
    LineCreate,
    LineUpdate,
    LineResponse,
    LineListResponse
)
from app.services.line_service import LineService
from schemas.auth_schemas import UserContext
import logging


log = logging.getLogger("uvicorn.error")
log.setLevel(logging.DEBUG)
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

@line_router.post("/", response_model=LineResponse, status_code=status.HTTP_201_CREATED)
async def create_line(
    data: LineCreate,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    line_service: LineService = Depends(get_line_service)
) -> LineResponse:
    try:
        return await line_service.create_line(tenant_id, data)
    except ValidationError as e:
        log.debug(f"\n\n @line_router.post Validation error: {e.errors()} \n\n")
        raise

@line_router.get("/", response_model=list[LineListResponse])
async def list_lines(
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    line_service: LineService = Depends(get_line_service)
) -> list[LineListResponse]:
    log.info(f"******** router lines current_user.tenant_id {current_user.tenant_id}")
    return await line_service.get_lines(tenant_id)


@line_router.get("/{line_id}", response_model=LineResponse)
async def get_line(
    line_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    line_service: LineService = Depends(get_line_service)
) -> LineResponse:
    return await line_service.get_line(line_id, tenant_id)


@line_router.patch("/{line_id}", response_model=LineResponse)
async def update_line(
    line_id: uuid.UUID,
    data: LineUpdate,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    line_service: LineService = Depends(get_line_service)
) -> LineResponse:
    return await line_service.update_line(line_id, tenant_id, data)


@line_router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(
    line_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    line_service: LineService = Depends(get_line_service)
) -> None:
    await line_service.delete_line(line_id, tenant_id)


