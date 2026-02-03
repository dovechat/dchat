from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.notifications import NotificationSettings, NotificationLog, NotificationType, NotificationChannel


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ NotificationSettings ============

    async def create_settings(self, tenant_id: UUID, data: dict) -> NotificationSettings:
        settings = NotificationSettings(tenant_id=tenant_id, **data)
        self.db.add(settings)
        await self.db.commit()
        await self.db.refresh(settings)
        return settings

    async def get_settings_by_id(self, settings_id: UUID, tenant_id: UUID) -> Optional[NotificationSettings]:
        stmt = select(NotificationSettings).where(
            and_(
                NotificationSettings.id == settings_id,
                NotificationSettings.tenant_id == tenant_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_settings(self, tenant_id: UUID) -> List[NotificationSettings]:
        stmt = select(NotificationSettings).where(
            NotificationSettings.tenant_id == tenant_id
        ).order_by(NotificationSettings.notification_type, NotificationSettings.channel)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_settings_by_type_and_channel(
            self,
            tenant_id: UUID,
            notification_type: NotificationType,
            channel: NotificationChannel
    ) -> Optional[NotificationSettings]:
        stmt = select(NotificationSettings).where(
            and_(
                NotificationSettings.tenant_id == tenant_id,
                NotificationSettings.notification_type == notification_type,
                NotificationSettings.channel == channel
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_settings(self, settings: NotificationSettings, data: dict) -> NotificationSettings:
        for key, value in data.items():
            if value is not None:
                setattr(settings, key, value)
        await self.db.commit()
        await self.db.refresh(settings)
        return settings

    async def delete_settings(self, settings: NotificationSettings) -> None:
        await self.db.delete(settings)
        await self.db.commit()

    # ============ NotificationLog ============

    async def create_log(self, tenant_id: UUID, data: dict) -> NotificationLog:
        log = NotificationLog(tenant_id=tenant_id, **data)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_logs(
            self,
            tenant_id: UUID,
            limit: int = 50,
            offset: int = 0,
            notification_type: Optional[NotificationType] = None
    ) -> List[NotificationLog]:
        stmt = select(NotificationLog).where(
            NotificationLog.tenant_id == tenant_id
        )

        if notification_type:
            stmt = stmt.where(NotificationLog.notification_type == notification_type)

        stmt = stmt.order_by(NotificationLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_enabled_settings_by_type(
            self,
            tenant_id: UUID,
            notification_type: NotificationType
    ) -> List[NotificationSettings]:
        """Получить все активные настройки для определенного типа уведомлений"""
        stmt = select(NotificationSettings).where(
            and_(
                NotificationSettings.tenant_id == tenant_id,
                NotificationSettings.notification_type == notification_type,
                NotificationSettings.enabled == True
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())