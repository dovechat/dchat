import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.utils import get_file_from_s3
from core.database import get_db
from notification.notification_caller import notify_connection_error

log = logging.getLogger(__name__)


class TelegramBotSender(BaseSender):
    """Отправка сообщений в Telegram Bot"""

    def __init__(self):
        self.bot_token = None
        self.line_id = None

    def set_bot_token(self, bot_token: str):
        self.bot_token = bot_token

    def set_line_id(self, line_id):
        self.line_id = line_id

    async def send(self, data: MessageCreate, db: AsyncSession = None) -> dict:
        """Отправить сообщение (текст или файл)"""
        log.info(f"\n\n +++++++++++++ TelegramBotSender.send data {data} \n\n")

        if not self.bot_token:
            raise ValueError("Bot token not set")

        url = f"{settings.tg_bot_send_url}/bot{self.bot_token}/"

        try:
            if data.media:
                return await self._send_file(data)
            else:
                return await self._send_text(data)
        except Exception as e:
            log.error(f"TelegramBotSender.send failed: {e}", exc_info=True)
            try:
                await notify_connection_error(self.line_id, channel_type="telegram_bot", db=db)
            except Exception as ne:
                log.error(f"notify_connection_error failed: {ne}")
            raise

    def extract_msg_id(self, result) -> str | None:
        return str(result.get("message_id")) if result else None

    async def _send_text(self, data: MessageCreate) -> dict:
        """Отправить текстовое сообщение"""
        log.info(f"\n\n =^=^=^=^=^=^=^= tg bot send  settings.load_test_mode {settings.load_test_mode} \n\n")
        if settings.load_test_mode:
            return {"ok": True, "mock": True}
        log.info(f"\n\n send TEXT")
        url = f"{settings.tg_bot_send_url}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": data.phone,
            "text": data.text
        }
        log.info(f"\n\n ======== tg bot send  url {url} payload {payload} \n\n")
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            result = response.json()
            if result.get("ok"):
                return result["result"]
            raise Exception(f"Telegram API error: {result}")

    async def _send_file(self, data: MessageCreate) -> dict:
        log.info(f"\n\n send FILE")
        result = None
        for m in data.media:
            file_bytes, filename = await get_file_from_s3(m["id"])
            mime_type = m.get("mime_type")
            if mime_type and mime_type.startswith('image/'):
                url = f"{settings.tg_bot_send_url}/bot{self.bot_token}/sendPhoto"
                files = {'photo': (filename, file_bytes, mime_type)}
            else:
                url = f"{settings.tg_bot_send_url}/bot{self.bot_token}/sendDocument"
                files = {'document': (filename, file_bytes, mime_type or 'application/octet-stream')}

            payload = {
                'chat_id': data.phone,
                'caption': data.text
            }

            log.info(f"\n\n +++++++++++++ TelegramBotSender.send_file url {url} payload {payload} \n\n")

            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=payload, files=files)
                result = response.json()
                if not result.get("ok"):
                    raise Exception(f"Telegram API error: {result}")
                result = result["result"]
        return result



    