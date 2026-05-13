import json
import uuid
import logging
from fastapi import HTTPException

from app.repositories.line_repo import LineRepository
from infra.crypto import decrypt
from app.schemas.line_schemas import ChannelType
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
        wid = instance_data.get("wid") or ""
        phone = wid.split("@")[0] if "@" in wid else wid
        log.info(f"------- phone {phone}")
        connection_error = "can't get number of scanning phone" if wid else None

        await self.channel_repo.update_connection_status(
            line_id=line_id,
            status="connected",
            channel_type=ChannelType.WHATSAPP_GREEN,
            connection_error=connection_error,
            phone=phone
        )
        # Обновляем connection_state в lines
        await self.line_repo.update_connection_state(
            line_id=line_id,
            state={"status": "connected"}
        )
        log.info(f"Line {line_id} connected via QR scan, phone: {phone}")

    async def process_vk_webhook(self, line_id: uuid.UUID, payload: dict):
        """Обработка вебхука от VK API"""
        # Проверяем существование линии
        line = await self.line_repo.get_by_id(line_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        event_type = payload.get("typeWebhook")
        log.info(f"VK webhook for line {line_id}, type: {event_type}")

        return await self._handle_vk(line_id, payload)
        

    async def _handle_vk(self, line_id: uuid.UUID, payload: dict):
        """VK линия подключена"""
        # Обновляем статус в channel_accounts
        log.info(f"------- payload {payload}")
        group_id = payload.get("group_id", None)

        channel_acc = await self.channel_repo.get_by_line_and_type(line_id, 'vk')
        log.info(f"\n\n *-**-*-*-*-*-*-*-*   WebhookService._handle_vk channel_acc {dir(channel_acc)}   \n\n ")
        creds_js = decrypt(channel_acc.credentials_encrypted.get("encrypted_data",""))
        creds = json.loads(creds_js)
        group_id_db = creds.get("group_id", "")
        confirmation_code = creds.get("confirmation_code", "")
        log.info(f"------- group_id {group_id} group_id_db {group_id_db} confirmation_code {confirmation_code}")
        connection_error = "can't get number of scanning phone" if group_id and group_id != group_id_db else None
        
        await self.channel_repo.update_connection_status(
            line_id=line_id,
            status="connected",
            channel_type=ChannelType.VK,
            connection_error=connection_error,
        )
        # Обновляем connection_state в lines
        await self.line_repo.update_connection_state(
            line_id=line_id,
            state={"status": "connected"}
        )
        log.info(f"Line {line_id} connected via VK")
        return confirmation_code


# Фабрика для Depends
async def get_webhook_service():
    from app.repositories.line_repo import LineRepository, ChannelAccountRepository
    from core.database import get_db

    async with get_db() as session:
        line_repo = LineRepository(session)
        channel_repo = ChannelAccountRepository(session)
        return WebhookService(line_repo, channel_repo)