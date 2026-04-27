import logging
from app.senders.base import BaseSender
from  app.schemas.chat_schemas import MessageCreate
from models.messages import Message

log = logging.getLogger(__name__)


class TelegramUserSender(BaseSender):
    """Отправка сообщений в Telegram User (номерной)"""

    def __init__(self, listener=None):
        self.listener = None  # будет устанавливаться извне

    def set_listener(self, listener):
        self.listener = listener

    async def send(self, data: MessageCreate) -> dict:
        """Отправить текстовое сообщение"""
        log.info("\n\n +++++++++++++ TelegramUserSender.send")
        log.info(f"\n\n +++++++++++++ TelegramUserSender.send  data {data}  \n\n")
        conversation_id = str(data.conversation_id)
        recipient = data.phone
        text = data.text

        if data.media:
            return await self.listener.send_file_user(data)
        else:
            return await self.listener.send_message_user(data)

        '''
        if data.media_id:
            return await self.listener.send_file_user(
                # conversation_id=str(data.conversation_id),
                # recipient=data.phone,
                # media_id=data.media_id,
                # caption=data.text,
                # filename=data.raw_content["file_name"] 
            )
        else:
            return await self.listener.send_message_user(
                conversation_id=conversation_id,
                recipient=recipient,
                text=text
            )
        '''