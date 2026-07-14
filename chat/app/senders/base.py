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

    async def edit(self, channel_msg_id: str, phone: str, text: str) -> dict:
        raise NotImplementedError

    async def delete(self, channel_msg_id: str, phone: str) -> dict:
        raise NotImplementedError