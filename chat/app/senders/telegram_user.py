import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.senders.base import BaseSender
from  app.schemas.chat_schemas import MessageCreate


log = logging.getLogger(__name__)

class TelegramUserSender(BaseSender):
    """Отправка сообщений в Telegram User (номерной)"""

    def __init__(self, listener=None):
        self.listener = None  # будет устанавливаться извне
        self.line_id = None

    def set_listener(self, listener):
        self.listener = listener

    def extract_msg_id(self, result) -> str | None:
        return str(result.id) if result else None

    def set_line_id(self, line_id):
        self.line_id = line_id

    async def send(self, data: MessageCreate, db: AsyncSession = None) -> dict:
        log.info(f"TelegramUserSender.send data={data}")
        try:
            if data.media:
                return await self.listener.send_file_user(data)
            else:
                return await self.listener.send_message_user(data)
        except Exception as e:
            log.error(f"TelegramUserSender.send failed: {e}")
            try:
                await notify_connection_error(self.line_id, channel_type="telegram_user", db=db)
            except Exception as ne:
                log.error(f"notify_connection_error failed: {ne}")
            raise
