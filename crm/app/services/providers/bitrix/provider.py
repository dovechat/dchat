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
        tokens = await BitrixClient.refresh_tokens(
            domain=self.conn.domain,
            refresh_token=decrypt(self.conn.refresh_token_enc),
            client_id=decrypt(self.conn.bitrix_client_id_enc),
            client_secret=decrypt(self.conn.bitrix_client_secret_enc),
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
        chat_id = f"{self.conn.connector_id}_conv{conversation_id}"
        return await bx.send_message(
            connector_id=self.conn.connector_id,
            line_id=self.conn.crm_line_id,
            user_id=client_phone,
            user_name=client_name or self.conn.channel_type,
            chat_id=chat_id,
            text=text,
            message_id=message_id,
            crm_chat_id=crm_chat_id,
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

    async def edit_message(self, message_id: str, text: str) -> dict:
        bx = self._client()
        return await bx.edit_message_im(message_id=message_id, text=text)

    async def delete_message(self, message_id: str) -> dict:
        bx = self._client()
        return await bx.delete_message_im(message_id=message_id)
    
    