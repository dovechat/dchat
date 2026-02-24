from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from core.database import get_db
from app.services.member_service import MemberService
from app.schemas.member_schemas import (
    MemberCreate,
    MemberResponse,
    LinePermissionCreate,
    LinePermissionResponse
)
from core.dependencies import get_current_user
from models.tenants import User

members_router = APIRouter(prefix="/tenants/{tenant_id}/members", tags=["members"])

@members_router.post("", response_model=MemberResponse, status_code=201)
async def add_member(
    tenant_id: UUID,
    data: MemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Добавить сотрудника в тенант"""
    service = MemberService(db)
    return await service.add_member(tenant_id, data)

@members_router.get("", response_model=List[MemberResponse])
async def list_members(
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Список сотрудников тенанта"""
    service = MemberService(db)
    return await service.list_members(tenant_id, skip, limit)

@members_router.delete("/{user_id}", status_code=204)
async def remove_member(
    tenant_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Удалить сотрудника из тенанта"""
    service = MemberService(db)
    await service.remove_member(tenant_id, user_id)
    return None

@members_router.post("/line-permissions", response_model=LinePermissionResponse, status_code=201)
async def add_line_permission(
    tenant_id: UUID,
    data: LinePermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Выдать доступ к линии"""
    service = MemberService(db)
    return await service.add_line_permission(tenant_id, data)

@members_router.get("/line-permissions", response_model=List[LinePermissionResponse])
async def get_line_permissions(
    tenant_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить список доступов к линиям для сотрудника"""
    service = MemberService(db)
    return await service.get_line_permissions(tenant_id, user_id)

@members_router.delete("/line-permissions/{user_id}/{line_id}", status_code=204)
async def remove_line_permission(
    tenant_id: UUID,
    user_id: UUID,
    line_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Отозвать доступ к линии"""
    service = MemberService(db)
    await service.remove_line_permission(tenant_id, user_id, line_id)
    return None