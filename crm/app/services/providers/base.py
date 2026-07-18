"""Abstract CRM provider."""
from abc import ABC, abstractmethod
from models.crm import CrmAccount


class CrmProvider(ABC):
    def __init__(self, conn: CrmAccount):
        self.conn = conn

    @abstractmethod
    async def send_message(
        self,
        conversation_id: str,
        client_phone: str,
        client_name: str,
        text: str,
        message_id: str,
        crm_chat_id: str | None = None,
    ) -> dict: ...

    @abstractmethod
    async def handle_webhook(self, data: dict) -> dict: ...

    @abstractmethod
    async def refresh_tokens(self) -> dict:
        """Returns dict with new access_token and refresh_token."""
        ...
