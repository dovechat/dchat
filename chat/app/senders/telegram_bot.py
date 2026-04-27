import logging
import httpx
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.utils import get_file_from_s3

log = logging.getLogger(__name__)


class TelegramBotSender(BaseSender):
    """Отправка сообщений в Telegram Bot"""

    def __init__(self):
        self.bot_token = None

    def set_bot_token(self, bot_token: str):
        self.bot_token = bot_token

    async def send(self, data: MessageCreate) -> dict:
        """Отправить сообщение (текст или файл)"""
        log.info(f"\n\n +++++++++++++ TelegramBotSender.send data {data} \n\n")

        if not self.bot_token:
            raise ValueError("Bot token not set")

        url = f"https://api.telegram.org/bot{self.bot_token}/"

        if data.media:
            return await self._send_file(data)
        else:
            return await self._send_text(data)

    async def _send_text(self, data: MessageCreate) -> dict:
        """Отправить текстовое сообщение"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": data.phone,
            "text": data.text
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            result = response.json()
            if result.get("ok"):
                return result["result"]
            raise Exception(f"Telegram API error: {result}")

    async def _send_file(self, data: MessageCreate) -> dict:
        result = None
        for m in data.media:
            file_bytes, filename = await get_file_from_s3(m["id"])
            mime_type = m.get("mime_type")
            if mime_type and mime_type.startswith('image/'):
                url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
                files = {'photo': (filename, file_bytes, mime_type)}
            else:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
                files = {'document': (filename, file_bytes, mime_type or 'application/octet-stream')}

            payload = {
                'chat_id': data.phone,
                'caption': data.text
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=payload, files=files)
                result = response.json()
                if not result.get("ok"):
                    raise Exception(f"Telegram API error: {result}")
                result = result["result"]
        return result



    