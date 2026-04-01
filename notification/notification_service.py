"""NotificationService — send notifications via email, sms, telegram, internal."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from core.config import settings
from infra.email.sender import BaseEmailSender
from infra.sms.sender import SMSSender
from models.notifications import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from repo.line_repo import LineRepository
from notification.notification_repo import NotificationLogRepository, NotificationSettingsRepository

import logging
log = logging.getLogger("uvicorn.error")

TEMPLATES = {
    NotificationType.line_expiration: lambda ctx: f"Линия «{ctx['line_name']}» истекает {ctx['expires_at']}. Продлите подписку в личном кабинете.",
    NotificationType.line_connection_error: lambda ctx: f"Линия «{ctx['line_name']}» потеряла соединение. Проверьте настройки подключения.",
    NotificationType.line_blocked: lambda ctx: f"Линия «{ctx['line_name']}» заблокирована из-за недостатка средств. Пополните баланс.",
    NotificationType.low_balance: lambda ctx: f"Баланс заканчивается. Осталось средств на {ctx['days_left']} дн. Пополните баланс.",
    NotificationType.payment_success: lambda ctx: f"Платёж на сумму {ctx['amount']} успешно зачислен. Текущий баланс: {ctx['balance']}.",
}


class NotificationService:

    def __init__(
        self,
        settings_repo: NotificationSettingsRepository,
        log_repo: NotificationLogRepository,
    ) -> None:
        self.settings_repo = settings_repo
        self.log_repo = log_repo
        self._email = BaseEmailSender()
        self._sms = SMSSender()

    async def send(
        self,
        tenant_id: uuid.UUID,
        notification_type: NotificationType,
        context: dict[str, Any],
    ) -> None:
        enabled = await self.settings_repo.get_enabled(tenant_id, notification_type)
        if not enabled:
            return

        message = TEMPLATES[notification_type](context)

        for setting in enabled:
            log.info(
                f"\n\n ------- DEBUG send {tenant_id} type={notification_type} channel={setting.channel} target={setting.target} ---------- \n\n")
            log_entry = await self.log_repo.add_entry(
                tenant_id=tenant_id,
                notification_type=notification_type,
                channel=setting.channel,
                target=setting.target,
                message=message,
            )
            try:
                match setting.channel:
                    case NotificationChannel.email:
                        ok = self._send_email(setting.target, message)
                    case NotificationChannel.sms:
                        ok = self._send_sms(setting.target, message)
                    case NotificationChannel.telegram:
                        ok = self._send_telegram(setting.target, message)
                    case NotificationChannel.internal:
                        ok = True  # просто запись в лог, фронт сам подтянет

                await self.log_repo.update_status(
                    log_entry,
                    status=NotificationStatus.sent if ok else NotificationStatus.failed,
                    sent_at=datetime.now(timezone.utc).replace(tzinfo=None) if ok else None,
                )
            except Exception as e:
                log.error(f"\n\n ERROR !!! ------- Failed to send {setting.channel} notification to {setting.target}: {e} \n\n ---------- \n\n")
                await self.log_repo.update_status(
                    log_entry,
                    status=NotificationStatus.failed,
                    error_message=str(e),
                )

    def _send_email(self, target: str, message: str) -> bool:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        html = f"<p>{message}</p>"
        msg = self._email._create_message(subject="DoveChat уведомление", html=html, to_email=target)
        return self._email._send_raw(msg)

    def _send_sms(self, target: str, message: str) -> bool:
        return self._sms.send(to_phone=target, message=message)

    def _send_telegram(self, target: str, message: str) -> bool:
        token = settings.notification_bot_token
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            with httpx.Client() as client:
                response = client.post(url, json={"chat_id": target, "text": message}, timeout=10.0)
                return response.status_code == 200
        except Exception as e:
            log.error(f"Telegram send error: {e}")
            return False

    async def notify_line_blocked(self, tenant_id: uuid.UUID, line_name: str) -> None:
        await self.send(
            tenant_id=tenant_id,
            notification_type=NotificationType.line_blocked,
            context={"line_name": line_name},
        )
    
    async def notify_line_expired(self, tenant_id: uuid.UUID, line_name: str, expires_at: datetime) -> None:
        await self.send(
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            context={"line_name": line_name, "expires_at": expires_at},
        )

    async def notify_low_balance(
        self, tenant_id: uuid.UUID, balance: Decimal, days_left: int
    ) -> None:
        await self.send(
            tenant_id,
            NotificationType.low_balance,
            {"balance": balance, "days_left": days_left},
        )

    async def notify_line_connection_error(self, tenant_id: uuid.UUID, line_name: str) -> None:
        await self.send(tenant_id, NotificationType.line_connection_error, {"line_name": line_name})


