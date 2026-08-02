import httpx
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from notification.notification_caller import notify_connection_error
from app.senders.base import BaseSender
from  app.schemas.chat_schemas import MessageCreate


log = logging.getLogger(__name__)

class TelegramUserSender(BaseSender):
    def __init__(self):
        self.line_id = None
        self.conv_id = None

    def extract_msg_id(self, result) -> str | None:
        return result.get("channel_msg_id") if result else None

    def set_line_id(self, line_id):
        self.line_id = line_id

    def set_conv_id(self, conv_id):
        self.conv_id = conv_id

    async def send_(self, action: str, payload: dict):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://tg-connector:8000/{action}",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                if not result.get("status") or result.get("status") not in ("sent", "edited", "deleted"):
                    raise Exception(f"Telegram API error: {result}")
                return result

        except Exception as e:
            log.error(f"TelegramUserSender.send failed: {e}")
            try:
                await notify_connection_error(
                    self.line_id,
                    channel_type="telegram_user",
                    db=db,
                )
            except Exception as ne:
                log.error(f"notify_connection_error failed: {ne}")
            raise


    async def send(self, data: MessageCreate, db: AsyncSession = None) -> dict:
        log.info(f"\n\n TelegramUserSender.send data.media={data.media} \n\n")
        return await self.send_(
            action = "send",
            payload={
                "line_id": str(self.line_id),
                "phone": data.phone,
                "text": data.text,
                "media": data.media,
            },
        )

    async def edit(self, channel_msg_id: str, phone: str, text: str):
        # return await self.listener.edit_message_user(str(self.conv_id), phone, channel_msg_id, text)
        log.info(f"\n\n TelegramUserSender.edit channel_msg_id={channel_msg_id} phone={phone} text={text} \n\n")
        return await self.send_(
            action = "edit",
            payload={
                "line_id": str(self.line_id),
                "phone": phone,
                "channel_msg_id": channel_msg_id,
                "text": text,
            },
        )

    async def delete(self, channel_msg_id: str, phone: str):
        # return await self.listener.delete_message_user(self.line_id, phone, channel_msg_id)
        log.info(f"\n\n TelegramUserSender.delete channel_msg_id={channel_msg_id} phone={phone} \n\n")
        return await self.send_(
            action="delete",
            payload={
                "line_id": str(self.line_id),
                "phone": phone,
                "channel_msg_id": channel_msg_id,
            },
        )