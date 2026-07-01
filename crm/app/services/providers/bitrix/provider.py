"""Bitrix24 CRM provider."""
import logging
from infra.crypto import encrypt, decrypt
from crm.app.services.providers.base import CrmProvider
from crm.app.services.providers.bitrix.client import BitrixClient
from core.config import settings

log = logging.getLogger("uvicorn.error")


class BitrixProvider(CrmProvider):
    def _client(self) -> BitrixClient:
        return BitrixClient(self.conn.domain, decrypt(self.conn.access_token_enc))

    async def refresh_tokens(self) -> dict:
        from core.config import settings
        tokens = await BitrixClient.refresh_tokens(
            domain=self.conn.domain,
            refresh_token=decrypt(self.conn.refresh_token_enc),
            client_id=settings.BITRIX_CLIENT_ID,
            client_secret=settings.BITRIX_CLIENT_SECRET,
        )
        return {
            "access_token_enc": encrypt(tokens["access_token"]),
            "refresh_token_enc": encrypt(tokens["refresh_token"]),
        }

    async def send_message(
        self,
        conversation_id: str,
        client_phone: str,
        client_name: str,
        text: str,
        message_id: str,
        crm_chat_id: str | None = None,
        media: list[dict] = [],
    ) -> dict:
        bx = self._client()
        chat_id = f"{connector_id}_line{crm_line_id}"
        return await bx.send_message(
            connector_id=self.conn.connector_id,
            line_id=self.conn.crm_line_id,
            user_id=client_phone,
            user_name=client_name or self.conn.channel_type,
            chat_id=chat_id,
            text=text,
            message_id=message_id,
            media=media,
        )

    async def handle_webhook(self, data: dict) -> dict:
        msg_data = data.get("data", {}).get("MESSAGES", [{}])[0]
        user = msg_data.get("user", {})
        chat = msg_data.get("chat", {})
        message = msg_data.get("message", {})
        return {
            "client_phone": user.get("id", ""),
            "client_name": user.get("name", ""),
            "text": message.get("text", ""),
            "crm_chat_id": chat.get("id", ""),
        }
