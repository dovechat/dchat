"""amoCRM Chats API client."""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from email.utils import formatdate

import httpx

from core.config import settings

log = logging.getLogger("uvicorn.error")

AMOJO_URL = "https://amojo.amocrm.ru"
OAUTH_URL = "https://www.amocrm.ru/oauth2/access_token"


class AmoCrmClient:
    def __init__(self, channel_id: str, channel_secret: str, account_id: str):
        self.channel_id = channel_id
        self.channel_secret = channel_secret
        self.account_id = account_id
        self.scope_id = f"{channel_id}_{account_id}"

    def _sign(self, body: bytes) -> tuple[str, str, str]:
        date = formatdate(usegmt=True)
        md5 = hashlib.md5(body).hexdigest()
        sig = hmac.new(
            self.channel_secret.encode(),
            body,
            hashlib.sha1,
        ).hexdigest()
        return date, md5, sig

    def _headers(self, body: bytes) -> dict:
        date, md5, sig = self._sign(body)
        return {
            "Date": date,
            "Content-Type": "application/json",
            "Content-MD5": md5,
            "X-Signature": sig,
        }

    async def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode()
        url = f"{AMOJO_URL}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, content=body, headers=self._headers(body))
            log.info(f"AmoCrmClient POST {path} status={resp.status_code}")
            if not resp.is_success:
                log.error(f"AmoCrmClient error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def connect_account(self, title: str = "DoveChat") -> dict:
        payload = {"account_id": self.account_id}
        result = await self._post(
            f"/v2/origin/custom/{self.channel_id}/connect",
            payload,
        )
        log.info(f"AmoCrmClient connect_account account_id={self.account_id}")
        return result

    async def create_chat(
            self,
            conversation_id: str,
            client_id: str,
            client_name: str,
            client_phone: str | None = None,
    ) -> dict:
        payload = {
            "conversation_id": conversation_id,
            "user": {
                "id": client_id,
                "name": client_name or "Клиент",
                "profile": {"phone": client_phone} if client_phone else {},
            },
        }
        result = await self._post(
            f"/v2/origin/custom/{self.scope_id}/chats",
            payload,
        )
        log.info(
            f"AmoCrmClient create_chat conv={conversation_id}"
        )
        return result

    async def disconnect_account(self) -> dict:
        payload = {"account_id": self.account_id}
        body = json.dumps(payload, ensure_ascii=False).encode()
        url = f"{AMOJO_URL}/v2/origin/custom/{self.channel_id}/disconnect"
        date, md5, sig = self._sign(body)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                "DELETE",
                url,
                content=body,
                headers={
                    "Date": date,
                    "Content-Type": "application/json",
                    "Content-MD5": md5,
                    "X-Signature": sig,
                },
            )
            log.info(f"AmoCrmClient disconnect_account status={resp.status_code}")
            resp.raise_for_status()
            return resp.json() if resp.text else {}

    async def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        sender_name: str,
        text: str,
        message_id: str | None = None,
        phone: str | None = None,
        media: list[dict] | None = None,
    ) -> dict:
        msgid = message_id or str(uuid.uuid4())
        payload = {
            "account_id": self.account_id,
            "event_type": "new_message",
            "payload": {
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "msgid": msgid,
                "conversation_id": conversation_id,
                "sender": {
                    "id": sender_id,
                    "name": sender_name,
                    "profile": {"phone": phone or sender_id},
                },
                "message": {"type": "text", "text": text},
            },
        }
        if media:
            payload["payload"]["message"] = {
                "type": "file",
                "text": text,
                "media": media[0]["url"],
                "file_name": media[0].get("file_name", "file"),
                "file_size": media[0].get("file_size", 0),
            }
        result = await self._post(f"/v2/origin/custom/{self.scope_id}", payload)
        log.info(f"AmoCrmClient send_message msgid={msgid} conv={conversation_id}")
        return result

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(
            self.channel_secret.encode(),
            body.strip(),
            hashlib.sha1,
        ).hexdigest()
        log.info(f"/n/n verify_webhook expected={expected} got={signature.lower()} /n/n")
        return hmac.compare_digest(expected, signature.lower())

    @classmethod
    async def refresh_tokens(
        cls,
        domain: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://{domain}/oauth2/access_token",
                json={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "redirect_uri": redirect_uri,
                },
            )
            log.info(f"AmoCrmClient refresh_tokens domain={domain} status={resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
        if not data.get("access_token"):
            raise ValueError(f"Token refresh failed: {data}")
        return data

    async def create_chat(
            self,
            conversation_id: str,
            client_phone: str,
            client_name: str,
    ) -> dict:
        payload = {
            "conversation_id": conversation_id,
            "user": {
                "id": client_phone,
                "name": client_name or "Клиент",
                "profile": {"phone": client_phone},
            },
        }
        result = await self._post(
            f"/v2/origin/custom/{self.scope_id}/chats",
            payload,
        )
        log.info(f"AmoCrmClient create_chat conv={conversation_id}")
        return result


