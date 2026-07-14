import base64
import hashlib
import json
import os
import time
import uuid

import httpx

from core.config import settings
from infra.crypto import encrypt, decrypt
from app.schemas.vk_oauth_schemas import VKGroupOption

VK_AUTHORIZE_URL = "https://id.vk.com/authorize"
VK_TOKEN_URL = "https://id.vk.com/oauth2/auth"
VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"
STATE_TTL = 600


class VKOAuthService:
    def __init__(self, channel_repo, line_repo):
        self.channel_repo = channel_repo
        self.line_repo = line_repo

    def build_authorize_url(
        self,
        tenant_id: uuid.UUID,
        line_id: uuid.UUID,
    ) -> str:
        code_verifier = base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")

        state_raw = json.dumps({
            "tenant_id": str(tenant_id),
            "line_id": str(line_id),
            "code_verifier": code_verifier,
            "exp": int(time.time()) + STATE_TTL,
        })
        state = encrypt(state_raw)

        params = (
            f"client_id={settings.VK_OAUTH_CLIENT_ID}"
            f"&redirect_uri={settings.VK_OAUTH_REDIRECT_URI}"
            f"&response_type=code"
            f"&scope={settings.VK_OAUTH_SCOPE}"
            f"&state={state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        return f"{VK_AUTHORIZE_URL}?{params}"

    async def handle_callback(
        self,
        code: str,
        state: str,
    ) -> tuple[str, list[VKGroupOption]]:
        state_data = json.loads(decrypt(state))
        if state_data["exp"] < int(time.time()):
            raise ValueError("state_expired")

        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                VK_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.VK_OAUTH_CLIENT_ID,
                    # "client_secret": settings.VK_OAUTH_CLIENT_SECRET,
                    "redirect_uri": settings.VK_OAUTH_REDIRECT_URI,
                    "code": code,
                    "code_verifier": state_data["code_verifier"],
                },
            )
            token_resp.raise_for_status()
            token_json = token_resp.json()
            user_access_token = token_json["access_token"]

            groups_resp = await client.get(
                f"{VK_API_URL}/groups.get",
                params={
                    "access_token": user_access_token,
                    "extended": 1,
                    "filter": "admin",
                    "v": VK_API_VERSION,
                },
            )
            groups_resp.raise_for_status()
            items = groups_resp.json().get("response", {}).get("items", [])

        groups = [
            VKGroupOption(
                id=g["id"],
                name=g["name"],
                screen_name=g.get("screen_name", ""),
                photo_100=g.get("photo_100"),
            )
            for g in items
        ]

        payload_raw = json.dumps({
            "tenant_id": state_data["tenant_id"],
            "line_id": state_data["line_id"],
            "user_access_token": user_access_token,
            "exp": int(time.time()) + STATE_TTL,
        })
        payload = encrypt(payload_raw)
        return payload, groups

    async def confirm_group(self, payload: str, group_id: int):
        data = json.loads(decrypt(payload))
        if data["exp"] < int(time.time()):
            raise ValueError("payload_expired")

        # TODO: получение токена сообщества (community access_token) —
        # у VK это отдельный обмен (group_ids + scope manage/messages при
        # авторизации сообщества), не совпадает 1:1 с user-token флоу выше.
        # Нужно свериться с актуальной VK ID for Business доке перед боевым запуском.
        # На этом этапе временно сохраняем user_access_token как access_token.
        creds_dict = {
            "access_token": data["user_access_token"],
            "group_id": group_id,
            "server_id": None,
        }
        encrypted = encrypt(json.dumps(creds_dict))

        line_id = uuid.UUID(data["line_id"])
        account = await self.channel_repo.get_by_line_and_type(line_id, "vk")
        if account:
            return await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        return await self.channel_repo.create_account(line_id=line_id, credentials_encrypted=encrypted)