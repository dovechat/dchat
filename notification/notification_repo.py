"""NotificationRepository — CRUD for NotificationSettings and NotificationLog."""
import uuid
from datetime import datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.notifications import (
    NotificationSettings,
    NotificationLog,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)
from repo.base import BaseRepository


class NotificationSettingsRepository(BaseRepository[NotificationSettings]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NotificationSettings, session)

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> list[NotificationSettings]:
        return await self.get_multi(filters={"tenant_id": tenant_id})

    async def get_enabled(
        self,
        tenant_id: uuid.UUID,
        notification_type: NotificationType,
    ) -> list[NotificationSettings]:
        return await self.get_multi(
            filters={
                "tenant_id": tenant_id,
                "notification_type": notification_type,
                "enabled": True,
            }
        )


class NotificationLogRepository(BaseRepository[NotificationLog]):

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NotificationLog, session)

    async def add_entry(
        self,
        tenant_id: uuid.UUID,
        notification_type: NotificationType,
        channel: NotificationChannel,
        target: str,
        message: str,
    ) -> NotificationLog:
        return await self.create(
            tenant_id=tenant_id,
            notification_type=notification_type,
            channel=channel,
            target=target,
            message=message,
            status=NotificationStatus.pending,
        )

    async def update_status(
            self,
            log_entry: NotificationLog,
            status: NotificationStatus,
            error_message: str | None = None,
            sent_at: datetime | None = None,
    ) -> None:
        await self.update(
            log_entry,
            status=status,
            error_message=error_message,
            sent_at=sent_at,
        )