import logging
import httpx
import json
import uuid
import random
from contextlib import asynccontextmanager
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.redis import rdb
from infra.crypto import decrypt
from notification.notification_caller import notify_connection_error
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

    def __init__(self, access_token: str, line_id=None, db: AsyncSession = None):
        self.access_token = access_token
        self.line_id = line_id
        self.db = db

    async def call(self, method: str, params: dict) -> dict:
        log.info(f"\n\n *=*=*=*=*=*== VkConnection.call params {params} \n\n")
        url = f"{VK_API_URL}/{method}"
        params = {**params, "access_token": self.access_token, "v": VK_API_VERSION}
        log.info(f"\n\n *=*=*=*=*=*== VkConnection.call params {params} \n\n")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=params)
                resp.raise_for_status()
                result = resp.json()
                if result.get("error"):
                    log.error(f"VK API error full: {result['error']}")
                    raise ValueError(f"VK API error: {result['error']['error_msg']}")
                return result.get("response")
        except Exception as e:
            log.error(f"VkConnection.call failed: {e}")
            try:
                await notify_connection_error(self.line_id, channel_type="vk", db=self.db)
            except Exception as ne:
                log.error(f"notify_connection_error failed: {ne}")
            raise

    async def _upload_file(
            self, upload_url: str, field_name: str, filename: str, file_bytes: bytes, expected_key: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(upload_url, files={
                field_name: (filename, file_bytes, "image/jpeg" if field_name == "photo" else None)})
            resp.raise_for_status()
            uploaded = resp.json()
        if expected_key not in uploaded:
            log.error(f"VK upload failed, response: {uploaded}")
            raise ValueError(f"VK upload failed: {uploaded}")
        log.info(f"VK doc upload response: {uploaded}")
        return uploaded


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
        upload_server = await self.call("photos.getMessagesUploadServer", {"peer_id": peer_id})
        upload_url = upload_server["upload_url"]

        uploaded = await self._upload_file(upload_url, "photo", filename, file_bytes, "photo")

        saved = await self.call("photos.saveMessagesPhoto", {
            "photo": uploaded["photo"],
            "server": uploaded["server"],
            "hash": uploaded["hash"],
        })
        photo = saved[0]
        return f"photo{photo['owner_id']}_{photo['id']}"

    async def upload_and_send_doc(self, peer_id: int, file_bytes: bytes, filename: str) -> str:
        upload_server = await self.call("docs.getMessagesUploadServer", {"peer_id": peer_id})
        upload_url = upload_server["upload_url"]

        uploaded = await self._upload_file(upload_url, "file", filename, file_bytes, "file")

        saved = await self.call("docs.save", {
            "file": uploaded["file"],
            "title": filename,
        })
        doc = saved.get("doc") or saved[0]
        return f"doc{doc['owner_id']}_{doc['id']}"

    async def edit_message(self, peer_id: int, message_id: int, text: str) -> dict:
        return await self.call("messages.edit", {
            "peer_id": peer_id,
            "message_id": message_id,
            "message": text,
        })
    
    async def delete_message(self, peer_id: int, message_id: int) -> dict:
        log.info("\n\n ---++--- VK listener delete_message -- \n\n")
        return await self.call("messages.delete", {
            "peer_id": peer_id,
            "message_ids": message_id,
            "delete_for_all": 1,
        })


class VkListener:
    """Обработчик вебхуков от VK Callback API"""

    def __init__(self):
        self.connections: Dict[str, VkConnection] = {}
        self.storage = StorageService()
        log.info("VkListener initialized")

    async def _handle_edited_message(self, line_id: str, payload: dict, chat_service: "ChatService", db: AsyncSession):
        log.info("VK _handle_edited_message start")
        msg = payload.get("object", {})
        if not msg:
            log.warning(f"No message in VK edit payload: {payload}")
            return

        log.info(f"VK _handle_edited_message msg {msg}")

        msg_id = str(msg.get("conversation_message_id"))
        from_id = msg.get("from_id")
        text = msg.get("text", "")
        phone = str(from_id)

        conv = await chat_service.conv_repo.get_conversations_by_phone(line_id, phone, "vk")
        if not conv:
            return

        log.info(f"VK _handle_edited_message conv {conv}")

        msg_repo = MessageRepository(db)
        messages = await msg_repo.get_multi(filters={"channel_msg_id": msg_id, "conversation_id": conv.id})
        if not messages:
            return

        message = messages[0]
        await msg_repo.update(message, text=text)

        log.info(f"VK _handle_edited_message message {message}")

        crm_message_id = (message.raw_content or {}).get("crm_message_id")

        log.info(f"VK _handle_edited_message crm_message_id {crm_message_id}")
        
        if message and not crm_message_id:
            crm_message_id = message.id

        if crm_message_id:
            try:
                from crm.app.services.crm_service import CrmService
                from crm.app.core.uow import CrmUnitOfWork
                crm_uow = CrmUnitOfWork(db)
                crm_service = CrmService(crm_uow)
                line = await crm_uow.lines.get_by_id(line_id)
                await crm_service.edit_to_crm(
                    tenant_id=line.tenant_id,
                    conversation_id=conv.id,
                    message_id=str(crm_message_id),
                    text=text,
                    channel_type="vk",
                )
            except Exception as e:
                log.error(f"CRM edit_to_crm failed: {e}")

        await manager.send_message_update(str(conv.id), {
            "type": "edit",
            "message_id": str(message.id),
            "text": text,
        })


    from core.metrics import prometheus_metrics

    @prometheus_metrics("vk")
    async def handle_webhook(self, line_id: str, payload: dict):
        from app.services.chat_service import ChatService

        creds = await self._get_creds(line_id)
        if payload.get("secret") != creds.get("secret_key"):
            log.warning(f"Invalid VK secret for line {line_id}")
            return "ok"  # VK ждёт 200, не 4xx, иначе ретраит и может отключить callback

        event_type = payload.get("type")

        if event_type == "message_new":
            async with get_session() as db:
                chat_service = ChatService(db)
                return await self._handle_incoming_message(line_id, payload, chat_service, db)
        elif event_type == "message_reply":
            from_id = payload.get("object", {}).get("from_id", 0)
            if from_id > 0:
                async with get_session() as db:
                    chat_service = ChatService(db)
                    return await self._handle_incoming_message(line_id, payload, chat_service, db)
            return await self.vk_handle_reply(line_id, payload)
        elif event_type == "confirmation":
            return await self.vk_confirm(line_id)
        elif event_type == "message_edit":
            async with get_session() as db:
                chat_service = ChatService(db)
                return await self._handle_edited_message(line_id, payload, chat_service, db)
        elif event_type == "message_delete":
            log.info("\n\n - --  --  -- event_type message_delete \n\n")
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

    @staticmethod
    def detect_image_mime(data: bytes) -> str | None:
        if data[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image/webp'
        return None

    async def _handle_incoming_message(self, line_id: str, payload: dict, chat_service: "ChatService", db: AsyncSession ):
        log.info(f"\n\n _handle_incoming_message payload {payload} \n\n")
        msg = payload.get("object", {}).get("message", {})
        if not msg:
            log.warning(f"No message in VK payload: {payload}")
            return "ok"

        msg_id =  str(msg.get("conversation_message_id"))
        from_id = msg.get("from_id")
        text = msg.get("text", "")
        attachments = msg.get("attachments", [])

        dedup_key = f"vk_msg:{msg_id}"
        if await rdb.get(dedup_key):
            return "ok"
        await rdb.set(dedup_key, "1", ex=300)

        phone = str(from_id)

        conv = await chat_service.conv_repo.get_conversations_by_phone(line_id, phone, "vk")
        if not conv:
            log.warning(f"Conversation not found for line {line_id}, from_id {from_id}")
            return "ok"
        conv_id = conv.id

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
                    detected_mime = self.detect_image_mime(file_bytes)
                    ext = detected_mime.split("/")[-1] if detected_mime else "jpg"
                    fname = f"{att_obj.get('id')}.{ext}"
                    await self.storage.save_file(file_bytes, m_id, fname, detected_mime or "application/octet-stream")
                    media_items.append(
                        {"id": str(m_id), "file_name": fname, "mime_type": detected_mime or "application/octet-stream",
                         "url": self.storage.presigned_url(m_id)}
                    )
            elif att_type == "doc":
                file_bytes = await self._download_file(att_obj.get("url"))
                fname = att_obj.get("title")
                mtype = att_obj.get("mime_type", "application/octet-stream")
                await self.storage.save_file(file_bytes, m_id, fname, mtype)
                media_items.append({"id": str(m_id), "file_name": fname, "mime_type": mtype, "url": self.storage.presigned_url(m_id)})

        message = await chat_service.save_incoming_vk(
            conversation_id=conv_id,
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

        await manager.send_new_message(conv_id, ws_message)

        try:
            from crm.app.services.crm_service import CrmService
            from crm.app.core.uow import CrmUnitOfWork
            crm_uow = CrmUnitOfWork(db)
            crm_service = CrmService(crm_uow)
            line = await crm_uow.lines.get_by_id(line_id)
            bx_chat = await crm_service.send_to_crm(
                tenant_id=line.tenant_id,
                conversation_id=conv_id,
                client_phone=phone,
                client_name="",
                text=text or "",
                message_id=str(message.id),
                channel_type="vk",
                media=media_items,
            )
            log.info(f"send_to_crm bx_chat={bx_chat}")
            if bx_chat:
                bx_chat_id = bx_chat[0]
                log.info(f"send_to_crm bx_chat_id={bx_chat_id}")
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