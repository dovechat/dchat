import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext
from account.app.repositories.notification_repo import NotificationRepository
from account.app.repositories.membership_repo import MembershipRepository
from account.app.services.notification_service import NotificationService
from account.app.schemas.notification_schemas import (
    NotificationSettingsCreate,
    NotificationSettingsUpdate,
    NotificationSettingsResponse,
    NotificationLogResponse,
)
from models.notifications import NotificationType

auth_scheme = HTTPBearer()

router = APIRouter(
    tags=["Notifications"],
    prefix="/tenants/{tenant_id}/notifications",
    dependencies=[Depends(auth_scheme)]
)


def check_tenant_access(tenant_id: uuid.UUID, current_user: UserContext = Depends(get_current_user)):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Token tenant_id mismatch")
    return tenant_id


def get_notification_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    repo = NotificationRepository(db)
    membership_repo = MembershipRepository(db)
    return NotificationService(repo, membership_repo)


# ============ NotificationSettings ============

@router.post(
    "/settings",
    response_model= list[NotificationSettingsResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create notification settings"
)
async def create_notification_settings(
    data: NotificationSettingsCreate,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    try:
        settings = await service.create_settings(
            tenant_id=tenant_id,
            notification_type=data.notification_type,
            channel=data.channel,
            target=data.target,
            enabled=data.enabled,
            user_id=current_user.id,
        )
        return settings
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/settings",
    response_model=List[NotificationSettingsResponse],
    summary="Get all notification settings"
)
async def get_notification_settings(
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.get_all_settings(tenant_id)


@router.get(
    "/settings/{settings_id}",
    response_model=NotificationSettingsResponse,
    summary="Get notification settings by ID"
)
async def get_notification_settings_by_id(
    settings_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    settings = await service.get_settings_by_id(settings_id, tenant_id)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification settings not found"
        )
    return settings


@router.patch(
    "/settings/{settings_id}",
    response_model=NotificationSettingsResponse,
    summary="Update notification settings"
)
async def update_notification_settings(
    settings_id: uuid.UUID,
    data: NotificationSettingsUpdate,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    try:
        settings = await service.update_settings(
            settings_id=settings_id,
            tenant_id=tenant_id,
            enabled=data.enabled,
            target=data.target,
        )
        return settings
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete(
    "/settings/{settings_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete notification settings"
)
async def delete_notification_settings(
    settings_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    try:
        await service.delete_settings(settings_id, tenant_id, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


# ============ NotificationLog ============

@router.get(
    "/history",
    response_model=List[NotificationLogResponse],
    summary="Get notification history"
)
async def get_notification_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    notification_type: Optional[NotificationType] = Query(None),
    tenant_id: uuid.UUID = Depends(check_tenant_access),
    current_user: UserContext = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.get_notification_history(
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        notification_type=notification_type,
    )