"""amoCRM provider."""
import httpx
import logging
from infra.crypto import encrypt, decrypt
from crm.app.services.providers.base import CrmProvider
from crm.app.services.providers.amocrm.client import AmoCrmClient
from core.config import settings


log = logging.getLogger("uvicorn.error")


class AmoCrmProvider(CrmProvider):
    def _client(self) -> AmoCrmClient:
        return AmoCrmClient(
            channel_id=settings.AMO_CHANNEL_ID,
            channel_secret=settings.AMO_CHANNEL_SECRET,
            account_id=self.conn.amojo_id,
        )

    async def refresh_tokens(self) -> dict:
        tokens = await AmoCrmClient.refresh_tokens(
            domain=self.conn.domain,
            refresh_token=decrypt(self.conn.refresh_token_enc),
            client_id=settings.AMO_CLIENT_ID,
            client_secret=settings.AMO_CLIENT_SECRET,
            redirect_uri=settings.AMO_REDIRECT_URI,
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
        client = self._client()
        if not crm_chat_id:
            chat = await client.create_chat(
                conversation_id=f"dc_{conversation_id}",
                client_phone=client_phone,
                client_name=client_name or "Клиент",
            )
            crm_chat_id = chat["id"]
        await client.send_message(
            conversation_id=crm_chat_id,
            sender_id=client_phone,
            sender_name=client_name or "Клиент",
            text=text,
            message_id=message_id,
            phone=client_phone,
            media=media or None,
        )
        return {"crm_chat_id": crm_chat_id}

    async def handle_webhook(self, data: dict) -> dict:
        return {
            "client_phone": data.get("receiver", ""),
            "client_name": data.get("receiver", ""),
            "text": data.get("text", ""),
            "crm_chat_id": data.get("conversation_id", ""),
        }

    async def get_lead_contact_phone(self, domain: str, access_token: str, lead_id: str) -> str | None:
        url = f"https://{domain}/api/v4/leads/{lead_id}?with=contacts"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            log.info(f"AmoCrmClient GET lead {lead_id} status={resp.status_code}")
            if not resp.is_success:
                log.error(f"AmoCrmClient error {resp.status_code}: {resp.text}")
                return None
            data = resp.json()
    
        contacts = data.get("_embedded", {}).get("contacts", [])
        if not contacts:
            return None
        contact_id = contacts[0]["id"]
    
        url2 = f"https://{domain}/api/v4/contacts/{contact_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp2 = await client.get(url2, headers=headers)
            if not resp2.is_success:
                return None
            contact_data = resp2.json()
    
        for field in contact_data.get("custom_fields_values") or []:
            if field.get("field_code") == "PHONE":
                return field["values"][0]["value"]
        return None