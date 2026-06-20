from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from  app.schemas.chat_schemas import MessageCreate

class BaseSender(ABC):
    """Базовый класс для отправки сообщений в разные каналы"""

    def extract_msg_id(self, result) -> str | None:
        return None

    @abstractmethod
    async def send(self, data: MessageCreate, db: AsyncSession) -> dict:
        """Отправить текстовое сообщение"""
        pass

#    @abstractmethod
#    async def send_file(self, conversation_id: str, recipient: str, file_data: dict, caption: str = None) -> dict:
#        """Отправить файл"""
#        pass