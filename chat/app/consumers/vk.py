import logging
import httpx
import json
import uuid
import random
from contextlib import asynccontextmanager
from typing import Dict
from core.database import get_db
from core.redis import rdb
from infra.crypto import decrypt
from repo.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository, LineRepository
from app.services.websocket_manager import manager
from models.messages import MessageDirection
from schemas.line_schemas import ChannelType
from services.storage_service import StorageService


log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"

class VkConnection:
    """Соединение с VK API для одной линии"""

    def __init__(self, access_token: str):
        self.access_token = access_token

    async def call(self, method: str, params: dict) -> dict:
        log.info(f"\n\n *=*=*=*=*=*== VkConnection.call params {params} \n\n")
        url = f"{VK_API_URL}/{method}"
        params = {**params, "access_token": self.access_token, "v": VK_API_VERSION}
        log.info(f"\n\n *=*=*=*=*=*== VkConnection.call params {params} \n\n")
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=params)
            resp.raise_for_status()
            result = resp.json()
            if result.get("error"):
                log.error(f"VK API error full: {result['error']}")
                raise ValueError(f"VK API error: {result['error']['error_msg']}")
            return result.get("response")

    async def send_message(self, peer_id: int, text: str, random_id: int) -> dict:
        return await self.call("messages.send", {
            "peer_id": peer_id,
            "message": text,
            "random_id": random_id,
        })

    async def send_file(self, peer_id: int, attachment: str, text: str = "") -> dict:
        return await self.call("messages.send", {
            "peer_id": peer_id,
            "message": text,
            "attachment": attachment,
            "random_id": random.randint(1, 2**31)
        })

    async def upload_and_send_photo(self, peer_id: int, file_bytes: bytes, filename: str) -> str:
        # 1. Получить upload_url для документа
        upload_server = await self.call("docs.getMessagesUploadServer", {"peer_id": peer_id})
        upload_url = upload_server["upload_url"]

        # 2. Загрузить файл
        async with httpx.AsyncClient() as client:
            resp = await client.post(upload_url, files={"file": (filename, file_bytes, "image/jpeg")})
            resp.raise_for_status()
            uploaded = resp.json()

        # 3. Сохранить
        saved = await self.call("docs.save", {
            "file": uploaded["file"],
            "title": filename,
        })
        doc = saved.get("doc") or saved[0]
        log.debug(saved)
        # 4. Отправить
        return f"doc{doc['owner_id']}_{doc['id']}"




class VkListener:
    """Обработчик вебхуков от VK Callback API"""

    def __init__(self):
        self.connections: Dict[str, VkConnection] = {}
        self.storage = StorageService()
        log.info("VkListener initialized")

    async def handle_webhook(self, line_id: str, payload: dict):
        from app.services.chat_service import ChatService

        event_type = payload.get("type")

        if event_type == "message_new":
            async with get_session() as db:
                chat_service = ChatService(db)
                return await self._handle_incoming_message(line_id, payload, chat_service)
        elif event_type == "message_reply":
            from_id = payload.get("object", {}).get("from_id", 0)
            if from_id > 0:
                async with get_session() as db:
                    chat_service = ChatService(db)
                    return await self._handle_incoming_message(line_id, payload, chat_service)
            return await self.vk_handle_reply(line_id, payload)
        elif event_type == "confirmation":
            return await self.vk_confirm(line_id)
        else:
            log.warning(f"Ignoring VK webhook type: {event_type}")

    async def vk_handle_reply(self, line_id, payload):
        msg = payload.get("object", {})
        if not msg:
            log.warning(f"No message in VK payload: {payload}")
            return

        log.info(f"\n\n +-+-+ vk_handle_reply payload {payload} \n\n")

        msg_id = int(msg.get("random_id"))
        from_id = msg.get("from_id")
        phone = str(from_id)

        async with get_session() as db:
            conv_repo = ConversationRepository(db)
            conv = await conv_repo.get_by_line_and_crm(line_id, "vk")
            log.info(f"\n\n *-*-* vk_handle_reply conv {conv} phone {phone} line_id {line_id}\n\n")
            log.info(f"\n\n *-*-* vk_handle_reply msg {msg} \n\n")

            msg_repo = MessageRepository(db)
            message = await msg_repo.get_by_id(msg_id)
            log.info(f"\n\n vk_handle_reply message {message} \n\n")
            log.info(f"message {message} ")
            if message:
                try:
                    await msg_repo.update(
                        message,
                        status="delivered"
                    )
                except Exception as e:
                    log.error(f"!!! --- ERROR --- VK vk_handle_reply can't update message status {e}")
    
                await manager.send_message_status(str(conv.id), {
                    "message_id": str(message.id),
                    "status": "delivered",
                })

        return 'ok'


    async def vk_confirm(self, line_id: uuid.UUID) -> str:
        creds = await self._get_creds(line_id)
        async with get_session() as db:
            channel_repo = ChannelAccountRepository(db)
            await channel_repo.update_connection_status(
                line_id=line_id,
                status="connected",
                channel_type=ChannelType.VK,
            )
            # Обновляем connection_state в lines
            line_repo = LineRepository(db)
            await line_repo.update_connection_state(
                line_id=line_id,
                state={"status": "connected"}
            )
        log.info(f"Line {line_id} connected via VK")
        return creds["confirmation_code"]

    async def _get_creds(self, line_id: uuid.UUID) -> dict:
        async with get_session() as db:
            repo = ChannelAccountRepository(db)
            account = await repo.get_by_line_and_type(line_id, "vk")
            if not account:
                raise ValueError(f"No VK channel account for line {line_id}")
            creds_json = decrypt(account.credentials_encrypted["encrypted_data"])
            return json.loads(creds_json)

    async def _handle_incoming_message(self, line_id: str, payload: dict, chat_service: "ChatService"):
        log.info(f"\n\n _handle_incoming_message payload {payload} \n\n")
        msg = payload.get("object", {}).get("message", {})
        if not msg:
            log.warning(f"No message in VK payload: {payload}")
            return

        msg_id = str(msg.get("id"))
        from_id = msg.get("from_id")
        text = msg.get("text", "")
        attachments = msg.get("attachments", [])

        dedup_key = f"vk_msg:{msg_id}"
        if await rdb.get(dedup_key):
            return
        await rdb.set(dedup_key, "1", ex=300)

        phone = str(from_id)

        conv = await chat_service.conv_repo.get_conversations_by_phone(line_id, phone, "vk")
        if not conv:
            log.warning(f"Conversation not found for line {line_id}, from_id {from_id}")
            return

        media_items = []

        for att in attachments:
            att_type = att.get("type")
            att_obj = att.get(att_type, {})
            m_id = uuid.uuid4()
            if att_type == "photo":
                sizes = att_obj.get("sizes", [])
                if sizes:
                    best = max(sizes, key=lambda s: s.get("width", 0))
                    file_bytes = await self._download_file(best.get("url"))
                    fname = f"{att_obj.get('id')}.jpg"
                    await self.storage.save_file(file_bytes, m_id, fname, "image/jpeg")
                    media_items.append({"id": str(m_id), "file_name": fname, "mime_type": "image/jpeg"})
            elif att_type == "doc":
                file_bytes = await self._download_file(att_obj.get("url"))
                fname = att_obj.get("title")
                mtype = att_obj.get("mime_type", "application/octet-stream")
                await self.storage.save_file(file_bytes, m_id, fname, mtype)
                media_items.append({"id": str(m_id), "file_name": fname, "mime_type": mtype})

        message = await chat_service.save_incoming_vk(
            conversation_id=conv.id,
            external_id=msg_id,
            text=text,
            msg_type="message_new",
            media_items=media_items or None,
        )

        ws_message = {
            "id": str(message.id),
            "text": message.text,
            "direction": "inbound",
            "created_at": message.created_at.isoformat(),
            "phone": phone
        }
        if media_items:
            ws_message["media"] = media_items

        await manager.send_new_message(conv.id, ws_message)

        async with get_session() as db:
            try:
                from crm.app.services.crm_service import CrmService
                from crm.app.core.uow import CrmUnitOfWork
                crm_uow = CrmUnitOfWork(db)
                crm_service = CrmService(crm_uow)
                line = await crm_uow.lines.get_by_id(line_id)
                bx_chat_id = await crm_service.send_to_crm(
                    tenant_id=line.tenant_id,
                    conversation_id=conv.id,
                    client_phone=phone,
                    client_name="",
                    text=text or "",
                    message_id=msg_id,
                    channel_type="vk",
                    media=media_items,
                )
                log.info(f"send_to_crm bx_chat_id={bx_chat_id}")
                if bx_chat_id:
                    await chat_service.conv_repo.update(conv, crm_chat_id=bx_chat_id)
            except Exception as e:
                log.error(f"CRM send_to_crm failed: {e}")
        return 'ok'

    async def _download_file(self, url: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def send_message(self, line_id: str, to: str, text: str) -> dict:
        if line_id not in self.connections:
            creds = await self._get_creds(line_id)
            log.info(f"\n\n *********** VK creds keys: {list(creds.keys())} \n\n")
            self.connections[line_id] = VkConnection(creds["access_token"])
        return await self.connections[line_id].send_message(int(to), text)

    async def send_file(self, line_id: str, to: str, file_url: str, caption: str = "") -> dict:
        connection = self.connections.get(line_id)
        if not connection:
            raise ValueError(f"No VK connection for line {line_id}")
        # VK не принимает прямые ссылки — нужна загрузка через docs API
        # TODO: реализовать upload + attachment string
        raise NotImplementedError("VK file sending not implemented yet")