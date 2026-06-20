from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from models.notifications import (
    NotificationSettings,
    NotificationLog,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)
from account.app.repositories.notification_repo import NotificationRepository


class NotificationService:
    def __init__(self, repo: NotificationRepository):
        self.repo = repo
        self.membership_repo = membership_repo
    # ============ NotificationSettings CRUD ============

    async def create_settings(
            self,
            tenant_id: UUID,
            user_id: UUID,
            notification_type: NotificationType,
            channel: NotificationChannel,
            target: str,
            enabled: bool = True,
    ) -> list[NotificationSettings]:
        memberships = await self.membership_repo.get_multi(filters={"user_id": user_id, "is_active": True})
        tenant_ids = [m.tenant_id for m in memberships]
        results = []
        for tid in tenant_ids:
            existing = await self.repo.get_settings_by_type_and_channel(tid, notification_type, channel)
            if existing:
                continue
            data = {
                "notification_type": notification_type,
                "channel": channel,
                "target": target,
                "enabled": enabled,
            }
            results.append(await self.repo.create_settings(tid, data))
        return results

    async def get_all_settings(self, tenant_id: UUID) -> List[NotificationSettings]:
        """Получить все настройки уведомлений тенанта"""
        return await self.repo.get_all_settings(tenant_id)

    async def get_settings_by_id(
            self,
            settings_id: UUID,
            tenant_id: UUID
    ) -> Optional[NotificationSettings]:
        """Получить настройку по ID"""
        return await self.repo.get_settings_by_id(settings_id, tenant_id)

    async def update_settings(
            self,
            settings_id: UUID,
            tenant_id: UUID,
            enabled: Optional[bool] = None,
            target: Optional[str] = None
    ) -> NotificationSettings:
        """Обновить настройку уведомлений"""
        settings = await self.repo.get_settings_by_id(settings_id, tenant_id)
        if not settings:
            raise ValueError("Notification settings not found")

        update_data = {}
        if enabled is not None:
            update_data["enabled"] = enabled
        if target is not None:
            update_data["target"] = target

        return await self.repo.update_settings(settings, update_data)

    async def delete_settings(self, settings_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        settings = await self.repo.get_settings_by_id(settings_id, tenant_id)
        if not settings:
            raise ValueError("Notification settings not found")

        memberships = await self.membership_repo.get_multi(filters={"user_id": user_id, "is_active": True})
        for m in memberships:
            s = await self.repo.get_settings_by_type_and_channel(m.tenant_id, settings.notification_type,
                                                                 settings.channel)
            if s:
                await self.repo.delete_settings(s)

    # ============ NotificationLog ============

    async def get_notification_history(
            self,
            tenant_id: UUID,
            limit: int = 50,
            offset: int = 0,
            notification_type: Optional[NotificationType] = None
    ) -> List[NotificationLog]:
        """Получить историю уведомлений"""
        return await self.repo.get_logs(tenant_id, limit, offset, notification_type)

    # ============ Отправка уведомлений (заглушка) ============

    async def send_notification(
            self,
            tenant_id: UUID,
            notification_type: NotificationType,
            message: str,
    ) -> List[NotificationLog]:
        """
        Отправить уведомление по всем активным каналам.
        Пока что это заглушка - только пишет в лог.
        В будущем здесь будет реальная отправка через email/telegram/sms.
        """
        # Получаем все активные настройки для данного типа уведомления
        settings_list = await self.repo.get_enabled_settings_by_type(tenant_id, notification_type)

        if not settings_list:
            # Если нет настроек - просто логируем, но не падаем
            print(f"No enabled notification settings for {notification_type.value} in tenant {tenant_id}")
            return []

        logs = []
        for settings in settings_list:
            # Создаем запись в логе
            log_data = {
                "notification_type": notification_type,
                "channel": settings.channel,
                "target": settings.target,
                "message": message,
                "status": NotificationStatus.sent,  # Пока сразу "sent"
                "sent_at": datetime.now(timezone.utc),
            }

            try:
                # TODO: Здесь будет реальная отправка
                # if settings.channel == NotificationChannel.email:
                #     await self._send_email(settings.target, message)
                # elif settings.channel == NotificationChannel.telegram:
                #     await self._send_telegram(settings.target, message)
                # elif settings.channel == NotificationChannel.sms:
                #     await self._send_sms(settings.target, message)

                log = await self.repo.create_log(tenant_id, log_data)
                logs.append(log)

            except Exception as e:
                # Если отправка упала - логируем ошибку
                log_data["status"] = NotificationStatus.failed
                log_data["error_message"] = str(e)
                log_data["sent_at"] = None
                log = await self.repo.create_log(tenant_id, log_data)
                logs.append(log)

        return logs