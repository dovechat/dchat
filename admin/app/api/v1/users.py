"""Admin API: users management."""
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.dependencies import AdminUser, DBSession
from app.core.uow import AdminUnitOfWork
from app.schemas.admin_schemas import (
    MessageResponse,
    ResetPasswordRequest,
    SetUserStatusRequest,
    UserListResponse,
    UserOut,
)
from app.services.tenant_service import AdminTenantService

router = APIRouter(prefix="/users", tags=["Admin — Users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    db: DBSession,
    admin: AdminUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    role: str | None = Query(None),
    status: str | None = Query(None),
    email: str | None = Query(None),
):
    """Список всех пользователей с фильтрацией."""
    uow = AdminUnitOfWork(db)
    service = AdminTenantService(uow)
    return await service.list_users(
        skip=skip,
        limit=limit,
        role=role,
        status=status,
        email=email,
        actor_id=UUID(admin["sub"]),
    )


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: UUID, db: DBSession, admin: AdminUser):
    """Детали пользователя."""
    uow = AdminUnitOfWork(db)
    service = AdminTenantService(uow)
    return await service.get_user(user_id, actor_id=UUID(admin["sub"]))


@router.patch("/{user_id}/status", response_model=MessageResponse)
async def set_user_status(
    user_id: UUID,
    request: SetUserStatusRequest,
    db: DBSession,
    admin: AdminUser,
):
    """Изменить статус пользователя (active / blocked / pending)."""
    uow = AdminUnitOfWork(db)
    service = AdminTenantService(uow)
    return await service.set_user_status(user_id, request, actor_id=UUID(admin["sub"]))


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
async def reset_password(
    user_id: UUID,
    request: ResetPasswordRequest,
    db: DBSession,
    admin: AdminUser,
):
    """Принудительный сброс пароля пользователя."""
    uow = AdminUnitOfWork(db)
    service = AdminTenantService(uow)
    return await service.reset_password(user_id, request, actor_id=UUID(admin["sub"]))