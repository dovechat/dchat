import logging
import httpx
import json
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional
from fastapi import Request
from core.database import get_db
from core.redis import rdb
from infra.crypto import decrypt
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository
from app.services.websocket_manager import manager
from models.messages import MessageDirection
from services.storage_service import StorageService


log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

# !!! --- change it on production --- !!!
WABA_API_URL = "https://waba-sandbox.360dialog.io/v1"

class WabaConnection:
    """Соединение с 360dialog API для одной линии"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "D360-API-KEY": api_key,
            "Content-Type": "application/json"
        }

    async def send(self, endpoint: str, payload: dict) -> dict:
        url = f"{WABA_API_URL}/{endpoint}"
        log.info(f"WabaConnection.send to {url}: {payload}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            log.error(f"WabaConnection.send failed: {e}")
            raise

    async def send_message(self, to: str, text: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return await self.send("messages", payload)

    async def send_template(self, to: str, template_name: str, language: str = "ru",
                            components: list | None = None) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components or [],
            },
        }
        return await self.send("messages", payload)


    async def send_file(self, to: str, file_url: str, mime_type: str | None = None, caption: str = "") -> dict:
        # Определяем тип медиа по расширению или mime_type
        # Упрощенно: считаем что это документ
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {
                "link": file_url,
                "caption": caption
            }
        }
        pl = {"link": file_url, "caption": caption}
        mime_main = mime_type.split("/")[0].replace("application", "document")
        payload["type"] = mime_main
        payload[mime_main] = pl

        log.info(f"\n\n ** consumers/waba WabaConnection.send_file payload {payload} \n\n")

        return await self.send("messages", payload)


class WabaListener:
    """Слушатель вебхуков от 360dialog (Meta Cloud API)"""

    def __init__(self):
        self.connections: Dict[str, WabaConnection] = {}
        self.storage = StorageService()
        log.info("WabaListener initialized")

    async def handle_webhook(self, line_id: str, payload: dict):
        from app.services.chat_service import ChatService

        # Парсим структуру Meta
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        if "messages" in value:
            async with get_session() as db:
                chat_service = ChatService(db)
                await self._handle_incoming_message(line_id, value, chat_service)

        elif "statuses" in value:
            await self._handle_message_status(line_id, value)
        else:
            log.warning(f"Unhandled webhook structure: {value.keys()}")

    async def download_media(self, media_url: str, api_key: str) -> bytes:  # передавай полный url из webhook
        log.info(f"\n\n ** WabaListener.download_media media_url {media_url} api_key {api_key} \n\n")
        
        if 'lookaside.fbsbx.com' in media_url:
            # Проксируем через 360dialog
            proxy_url = media_url.replace('https://lookaside.fbsbx.com', 'https://waba-v2.360dialog.io')
            # Убери лишние слеши если есть (иногда \\)
            proxy_url = proxy_url.replace('\\', '')

            headers = {"D360-API-KEY": api_key}
            async with httpx.AsyncClient() as client:
                resp = await client.get(proxy_url, headers=headers)
                log.info(f"\n\n ** WabaListener.download_media resp.status_code {resp.status_code} \n\n")
                if resp.status_code == 200:
                    return resp.content
                else:
                    raise Exception(f"Failed: {resp.status_code} - {resp.text}")

            # 3. Ничего не работает
            resp.raise_for_status()

    async def _handle_incoming_message(self, line_id: str, value: dict, chat_service: "ChatService"):
        async with get_session() as db:
            repo = ChannelAccountRepository(db)
            account = await repo.get_by_line_and_type(uuid.UUID(line_id), "waba")
            if not account:
                raise ValueError(f"No channel account for line {line_id}")
            creds = decrypt(account.credentials_encrypted["encrypted_data"])
            api_key = json.loads(creds)["api_key"]

        for msg in value.get("messages", []):
            msg_id = msg["id"]

            dedup_key = f"waba_msg:{msg_id}"
            if await rdb.get(dedup_key):
                continue
            await rdb.set(dedup_key, "1", ex=300)

            from_number = msg["from"]
            msg_type = msg["type"]

            text = None
            media_id = None
            file_name = None
            mime_type = None
            file_bytes = None

            if msg_type == "text":
                text = msg["text"]["body"]
            elif msg_type in ["image", "audio", "video", "document"]:
                media = msg.get(msg_type, {})
                log.info(f"Downloading media {media} with key {api_key[:5]}...")
                if "id" in media:
                    # Скачиваем из WABA
                    try:
                        file_bytes = await self.download_media(media["url"], api_key)
                        mime_type = media.get("mime_type")
                        file_name = media.get("filename")
                        media_id = uuid.uuid4()
                    except Exception as e:
                        log.error(f"ERROR: !!! --- Failed to download media {media_id}: {e}")
                        file_bytes = None
                        mime_type = None
                        file_name = None
                        media_id = None
                    # Сохраняем в MinIO
                    if file_bytes:
                        await self.storage.save_file(
                            file_bytes=file_bytes,
                            media_id=media_id,
                            filename=file_name or f"{media_id}.bin",
                            mime_type=mime_type
                        )
                text = media.get("caption", "")

            phone = f"+{from_number}"

            conv = await chat_service.conv_repo.get_conversations_by_phone(line_id, phone, "waba")
            if not conv:
                log.warning(f"Conversation not found for line {line_id}, phone {phone}")
                continue

            media_items = []
            if media_id:
                media_items = [{
                    "media_id": str(media_id),
                    "file_name": file_name,
                    "mime_type": mime_type,
                }]

            message = await chat_service.save_incoming_waba(
                conversation_id=conv.id,
                external_id=msg_id,
                text=text,
                media_items=media_items if media_items else None,
                raw_data=value,
            )

            ws_message = {
                "id": str(message.id),
                "text": message.text,
                "direction": "inbound",
                "created_at": message.created_at.isoformat(),
                "phone": phone,
                "media": media_items,
            }

            await manager.send_new_message(conv.id, ws_message)

    async def _handle_message_status(self, line_id: str, value: dict):
        """Обработка статусов сообщений"""
        for status_update in value.get("statuses", []):
            msg_id = status_update["id"]
            status = status_update["status"]
            if status == "failed":
                log.warning(f"Message {msg_id} failed, skipping status update")
                continue

            dedup_key = f"waba_status:{msg_id}:{status}"
            if await rdb.get(dedup_key):
                continue
            await rdb.set(dedup_key, "1", ex=300)

            async with get_session() as db:
                msg_repo = MessageRepository(db)
                msg = await msg_repo.get_message_by_channel_msg_id(msg_id)
                if msg:
                    await msg_repo.set_message_status(msg.id, status)
                    await manager.send_message_status(str(msg.conversation_id), {
                        "message_id": str(msg.id),
                        "status": status,
                        "mime_type": msg.raw_content.get("mime_type") if msg.raw_content else None
                    })

    async def send_message(self, line_id: str, to: str, text: str) -> dict:
        if line_id not in self.connections:
            async with get_session() as db:
                repo = ChannelAccountRepository(db)
                account = await repo.get_by_line(uuid.UUID(line_id))
                if not account:
                    raise ValueError(f"No channel account for line {line_id}")
                creds = decrypt(account.credentials_encrypted["encrypted_data"])
                api_key = json.loads(creds)["api_key"]
                self.connections[line_id] = WabaConnection(api_key)

        connection = self.connections.get(line_id)
        return await connection.send_message(to, text)

    async def send_file(self, line_id: str, to: str, file_url: str, caption: str = "") -> dict:
        connection = self.connections.get(line_id)
        if not connection:
            raise ValueError(f"No connection for line {line_id}")
        return await connection.send_file(to, file_url, caption)