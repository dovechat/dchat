import uuid
import logging
from fastapi import HTTPException

from app.repositories.line_repo import LineRepository
from repo.line_repo import ChannelAccountRepository

log = logging.getLogger(__name__)


class WebhookService:
    def __init__(
            self,
            line_repo: LineRepository,
            channel_repo: ChannelAccountRepository
    ):
        self.line_repo = line_repo
        self.channel_repo = channel_repo

    async def process_green_webhook(self, line_id: uuid.UUID, payload: dict):
        """Обработка вебхука от Green API"""
        # Проверяем существование линии
        line = await self.line_repo.get_by_id(line_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        event_type = payload.get("typeWebhook")
        log.info(f"Green webhook for line {line_id}, type: {event_type}")

        if event_type == "qrScanned":
            # QR отсканирован, обновляем статус
            await self._handle_qr_scanned(line_id, payload)
        else:
            log.warning(f"Ignoring webhook type: {event_type}")

    async def _handle_qr_scanned(self, line_id: uuid.UUID, payload: dict):
        """QR отсканирован - линия подключена"""
        # Обновляем статус в channel_accounts
        log.info(f"------- payload {payload}")
        instance_data = payload.get("instanceData", {})
        phone = instance_data.get("wid", "")  # или "phoneNumber"
        log.info(f"------- phone {phone}")

        await self.channel_repo.update_connection_status(
            line_id=line_id,
            status="connected",
            phone=phone
        )
        # Обновляем connection_state в lines
        await self.line_repo.update_connection_state(
            line_id=line_id,
            state={"status": "connected"}
        )
        log.info(f"Line {line_id} connected via QR scan, phone: {phone}")


# Фабрика для Depends
async def get_webhook_service():
    from app.repositories.line_repo import LineRepository, ChannelAccountRepository
    from core.database import get_db

    async with get_db() as session:
        line_repo = LineRepository(session)
        channel_repo = ChannelAccountRepository(session)
        return WebhookService(line_repo, channel_repo)