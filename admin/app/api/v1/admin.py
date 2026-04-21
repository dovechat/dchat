from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from core.database import get_db
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext as User

from  app.core.uow import AdminUnitOfWork
from app.services.admin_service import AdminLineService, AdminService
from app.schemas.admin_schemas import (
    BalanceAdjustmentRequest, ExtendLineRequest,
    InstanceCleanRequest, InstanceAdminResponse,
    LedgerEntryResponse, LineAdminResponse,
    LineUpdateRequest, TenantAdminResponse,
    TenantBlockRequest,    
)
from core.config import settings

router = APIRouter()

async def require_superadmin(current_user: User = Depends(get_current_user)):
    """
    Проверяет, является ли текущий пользователь администратором сервиса.
    Ожидаем роль 'admin' в поле role модели UserContext.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required. Role 'admin' needed."
        )
    return current_user


# --- Tenants ---
@router.get("/tenants", response_model=List[TenantAdminResponse])
async def list_tenants(
        skip: int = Query(0),
        limit: int = Query(50),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    tenants = await service.tenant_repo.get_multi(skip=skip, limit=limit)
    return tenants


@router.post("/tenants/{tenant_id}/block")
async def block_tenant(
        tenant_id: UUID,
        request: TenantBlockRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    await service.block_tenant(tenant_id, request.reason)
    await db.commit()
    return {"status": "blocked", "tenant_id": str(tenant_id)}


# --- Lines ---
@router.get("/lines", response_model=List[LineAdminResponse])
async def search_lines(
        status: Optional[str] = None,
        channel_type: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        skip: int = Query(0),
        limit: int = Query(50),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    filters = {}
    if status: filters["status"] = status
    if channel_type: filters["channel_type"] = channel_type
    if tenant_id: filters["tenant_id"] = tenant_id

    # Возвращает кортежи (Line, tenant_name), нужно замапить в схему
    raw_data = await service.get_lines_global(skip, limit, filters)

    result = []
    for line_obj, tenant_name in raw_data:
        item = LineAdminResponse.model_validate(line_obj)
        item.tenant_name = tenant_name
        result.append(item)
    return result


@router.post("/lines/{line_id}/extend")
async def extend_line(
        line_id: UUID,
        request: ExtendLineRequest,
        db: AsyncSession = Depends(get_db),
        admin: dict = Depends(require_superadmin)
):
    service = AdminLineService(AdminUnitOfWork(db))
    return await service.extend_line(line_id, request, actor_id=UUID(admin["sub"]))


# --- Instances ---
@router.get("/instances", response_model=List[InstanceAdminResponse])
async def list_instances(
        status: Optional[str] = None,
        skip: int = Query(0),
        limit: int = Query(50),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    filters = {"status": status} if status else {}
    instances = await service.instance_repo.get_multi(skip=skip, limit=limit, filters=filters)
    return instances


@router.post("/instances/{instance_id}/clean")
async def clean_instance(
        instance_id: UUID,
        request: InstanceCleanRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    await service.clean_instance(instance_id, force=request.force)
    await db.commit()
    return {"status": "cleaned", "instance_id": str(instance_id)}


# --- Billing ---
@router.post("/billing/adjust", response_model=LedgerEntryResponse)
async def manual_balance_adjustment(
        request: BalanceAdjustmentRequest,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    try:
        entry = await service.adjust_balance(
            tenant_id=request.tenant_id,
            amount=request.amount,
            balance_type=request.balance_type,
            description=request.description,
            reference_id=request.reference_id
        )
        await db.commit()
        return LedgerEntryResponse.model_validate(entry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/billing/ledger/{tenant_id}", response_model=List[LedgerEntryResponse])
async def get_tenant_ledger(
        tenant_id: UUID,
        skip: int = Query(0),
        limit: int = Query(50),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_superadmin)
):
    service = AdminService(db)
    entries = await service.billing_repo.get_multi(
        skip=skip,
        limit=limit,
        filters={"tenant_id": tenant_id}
        # В base.repo нужно убедиться, что сортировка по created_at desc работает, 
        # либо добавить явный order_by здесь через session
    )
    return entries