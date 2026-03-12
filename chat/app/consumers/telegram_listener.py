import asyncio
import httpx
import json
import logging
import os
import uuid
from typing import Callable, Dict

from datetime import timedelta
from io import BytesIO
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from core.config import settings
from core.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.repositories.line_repo import LineRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.chat_schemas import MessageCreate
from app.services.websocket_manager import manager
from app.services.chat_service import ChatService
from app.utils import get_file_from_s3
from models.messages import MessageDirection

log = logging.getLogger(__name__)


class TelegramConnection:
    def __init__(self, conversation_id: str, my_phone: str, peer_phone: str, message_callback: Callable):
        self.conversation_id = conversation_id
        self.my_phone = my_phone
        self.peer_phone = peer_phone
        self.message_callback = message_callback
        self.client = None
        self._running = False
        self._reconnect_delay = 1

        log.info(f"TelegramConnection created for {conversation_id}")

    def decrypt(self, enc_data: str) -> dict:
        """Decode  data from encoded strinig to dictionary"""
        # here should be some decoding algorythm
        log.info(f"+++++ telegram_listener decrypt enc_data  {type(enc_data)} {enc_data}")
        return enc_data
        

    async def get_session(self) -> str:
        from infra.crypto import decrypt
        log.info(f"Getting session for {self.my_phone}")
        async for db in get_db():
            chat_repo = ChatRepository(db)
            # enc_data = await chat_repo.get_session_by_phone(self.my_phone)
            log.info(f"-----*--- get_session phone {self.my_phone} conv_id {self.conversation_id}")
            # if self.phone:
            #    channes_acc = await chat_repo.get_channel_acc_by_phone(self.my_phone)
            #else:
            channes_acc = await chat_repo.get_channel_acc_by_conversation(self.conversation_id)

            # log.info(f"-------- get_session {self.my_phone} channes_acc  {type(channes_acc.credentials_encrypted)} {channes_acc.credentials_encrypted}")

            creds_enc = json.loads(decrypt(channes_acc.credentials_encrypted["encrypted_data"]))
            log.info(f"-------- session decrypted creds_enc {type(creds_enc)}  {creds_enc}")
            log.info(f"-------- get_session channes_acc {creds_enc} AFTER")

            session = creds_enc["session_string"]
            log.info(f"------ session {session}")
            log.info(f"-------- Session retrieved for {self.my_phone}: {'found' if session else 'not found'}")

            break

        # !!!!! ----------------- TEMPORARY set hardcoded session
        # session = "1ApWapzMBu7DSGz-U-HUo93VERLWICzHwUw0ktqcC3Lhnvd90np-xVAvdzj8mtdarRpJGD37tYE6rI9T6EDcLJMxnwOU0lKNvXnRC5Y3tdw7iT2e1hr4sxT1abupvKvKTuipZnE9elgTAM_5R3iCS4OhHxePKV7feIFgfPSr18oGykP_TUMlh8rrq5X0t4GZnxYZIFtQrkkivg0aVpQeIUV7JaRT6uZHWM9ZJ8n0UBZdByVEgyKNOg6Kg2_YETJMM8FDLjzfFjAly0eHgjROVAMaDrV12-BeTzSM6HqSD-9LZFhqz-sIa-fCFS-00n_6wR_09ZTWPD_vJe3L67Li0gETGcXTVzuI="
        return session



    async def connect(self):
        log.info(f"+++++++++ Connecting to Telegram for {self.conversation_id}")
        session_string = await self.get_session()
        if not session_string:
            raise ValueError(f"No session for {self.my_phone}")

        log.info(f"+++++++++ Creating TelegramClient for {self.my_phone}")
        self.client = TelegramClient(
            StringSession(session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
            auto_reconnect=True,
            connection_retries=5,
            retry_delay=1
        )

        log.info(f"+++++++++ Connecting client for {self.my_phone}...")
        await self.client.connect()
        log.info(f"+++++++++ Client connected, checking authorization for {self.my_phone}")

        if not await self.client.is_user_authorized():
            raise ValueError(f"Not authorized for {self.my_phone}")

        log.info(f"+++++++++ Client authorized for {self.my_phone}, setting up handler")

        @self.client.on(events.NewMessage)
        async def handler(event):
            await self._handle_message(event)

        self._running = True
        log.info(f"+++++++++ Connected: {self.conversation_id} (client: {self.client is not None})")

        async for db in get_db():
            line_repo = LineRepository(db)
            chat_repo = ChatRepository(db)
            conv = await chat_repo.get_conv_by_id(self.conversation_id)
            log.info(f"+++++++++ Update connection status in db: conv {conv} {conv.line_id})")
            await line_repo.set_line_status(conv.line_id, {"status": "connected"})
            await db.commit()
            log.info(f"+++++++++ Update connection status in db: after)")
            break


    async def disconnect(self):
        log.info(f"Disconnecting {self.conversation_id}")
        self._running = False
        if self.client:
            await self.client.disconnect()
            self.client = None
            log.info(f"Disconnected {self.conversation_id}")

    async def run(self):
        log.info(f"Run started for {self.conversation_id}")
        while self._running:
            try:
                log.info(f"Attempting to connect for {self.conversation_id}")
                await self.connect()
                log.info(f"Running until disconnected for {self.conversation_id}")
                await self.client.run_until_disconnected()
            except asyncio.CancelledError:
                log.info(f"Run cancelled for {self.conversation_id}")
                break
            except Exception as e:
                log.error(f"Connection error for {self.conversation_id}: {e}")
                await self.disconnect()
                log.info(f"Reconnecting in {self._reconnect_delay}s for {self.conversation_id}")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 300)
            else:
                log.info(f"Normal termination for {self.conversation_id}")
                break
        await self.disconnect()
        log.info(f"Run finished for {self.conversation_id}")

    async def _handle_message(self, event):
        # Проверка на дубликат
        if hasattr(self, 'processed_msgs') and event.id in self.processed_msgs:
            # log.info(f"Duplicate message {event.id}, skipping")
            return
        if not hasattr(self, 'processed_msgs'):
            self.processed_msgs = set()
        self.processed_msgs.add(event.id)
        if len(self.processed_msgs) > 1000:
            self.processed_msgs = set(list(self.processed_msgs)[-500:])

        if not event.is_private:
            # log.info(f"Not private, skipping")
            return

        if not event.out:
            sender = await event.get_sender()
            if not sender:
                log.info(f"No sender, skipping")
                return
            sender_phone = getattr(sender, 'phone', '') or ''
            log.info(f"Incoming from {sender_phone}, expected {self.peer_phone}")
            if sender_phone.lstrip('+') != self.peer_phone.lstrip('+'):
                log.info(f"Phone mismatch, skipping")
                return
        else:
            # Это своё сообщение — игнорируем
            log.info(f"Own message, skipping")
            return

        log.info(f"Message handler triggered for {self.conversation_id} event {event}")

        log.info(f"Calling message_callback for {self.conversation_id}")
        async for db in get_db():
            await self.message_callback(db, self.conversation_id, self.peer_phone, event)
            break
        

    async def wait_for_client(self, timeout=30):
        log.info(f"Waiting for client for {self.conversation_id}")
        start = asyncio.get_event_loop().time()
        while self.client is None and self._running:
            if asyncio.get_event_loop().time() - start > timeout:
                log.error(f"Timeout waiting for client for {self.conversation_id}")
                raise TimeoutError("Client connection timeout")
            await asyncio.sleep(0.1)
        if self.client is None:
            raise RuntimeError(f"Client is None for {self.conversation_id}")
        log.info(f"Client obtained for {self.conversation_id}")
        return self.client


class TelegramListener:
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.clients: Dict[str, TelegramClient] = {}
        self.bots: Dict[str, TelegramClient] = {}
        self.s3_client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure
        )
        log.info("TelegramListener initialized")

    async def start_listening(self, conversation_id: str, my_phone: str, peer_phone: str):
        log.info(f"******* TelegramListener.start_listening start_listening: conv={conversation_id}, my={my_phone}, peer={peer_phone}")
        if my_phone is None:
            # Это бот — не запускаем слушатель
            log.info(f"*********** Bot detected for {conversation_id}, skipping listener")
            return

        log.info(f"start_listening called for {conversation_id}")
        if conversation_id in self.tasks:
            task = self.tasks[conversation_id]
            if not task.done():
                log.info(f"Already listening for {conversation_id}")
                return
            log.info(f"Removing dead task for {conversation_id}")
            del self.tasks[conversation_id]

        log.info(f"Started listening: tasks --")
        task = asyncio.create_task(
            self._listen_task(conversation_id, my_phone, peer_phone),
            name=f"listener_{conversation_id}"
        )
        log.info(f"Started listening: task {task}")
        self.tasks[conversation_id] = task
        log.info(f"Started listening: self.tasks {self.tasks }")
        log.info(f"Started listening: conversation={conversation_id} my={my_phone} peer={peer_phone}")

    async def stop_listening(self, conversation_id: str):
        log.info(f"stop_listening called for {conversation_id}")
        task = self.tasks.pop(conversation_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info(f"Stopped listening for {conversation_id}")

    async def send_message_user(self, data: MessageCreate):
        log.info(f"*********** TelegramListener.send_message_user self.clients {self.clients} {type(self.clients)} {type(data.conversation_id)}")
        log.info(f"*********** TelegramListener.send_message_user for {data.conversation_id} to {data.phone}")
        client = self.clients.get(str(data.conversation_id))
        log.info(f"*********** TelegramListener.send_message_user client {client}")
        if not client:
            log.info(f"No client for {data.conversation_id}, waiting...")
            for i in range(30):
                await asyncio.sleep(0.1)
                client = self.clients.get(data.conversation_id)
                if client:
                    log.info(f"Client appeared for {data.conversation_id} after {i * 0.1}s")
                    break
            else:
                log.error(f"No client for {data.conversation_id} after waiting")
                return

        me = await client.get_me()
        # print(me.id, me.username, me.phone)
        log.info(f"TelegramListener Message sending to data.phone {data.phone} from me.phone {me.phone}")
        if not data.phone:
            data.phone = me.phone
        

        try:
            # Явно получаем entity и отправляем


            entity = await client.get_entity(data.phone)
            log.info(f"--------------- TelegramListener Entity for {data.phone}: {entity.id} - {getattr(entity, 'phone', 'no phone')}")
            log.info(f"Entity resolved: {type(entity).__name__}")
            log.info(f"------------------- TelegramListener Sending to entity: {entity.id}")
            sent = await client.send_message(entity, data.text)
            log.info(f"TelegramListener Message sent successfully to {data.phone}")
            return sent
        except Exception as e:
            log.error(f"TelegramListener Failed to send message to {data.phone}: {e}", exc_info=True)
            raise  # или вернуть False

    async def send_file_user(self, data: MessageCreate):
        """Отправить файл из S3 по media_id"""
        log.info(f"------------------- TelegramListener send_file_user start")
        conversation_id = str(data.conversation_id)
        filename = data.raw_content.get("file_name")
        client = self.clients.get(conversation_id)
        
        if not client:
            for i in range(30):
                await asyncio.sleep(0.1)
                client = self.clients.get(conversation_id)
                if client:
                    break
            else:
                log.error(f"No client for {conversation_id} after waiting")
                return

        file_bytes, _ = await get_file_from_s3(data.media_id)
        log.info(f"------------------- TelegramListener send_file_user client {client}")
        file_stream = BytesIO(file_bytes)
        file_stream.name = filename

        log.info(f"------------------- TelegramListener send_file_user: filename {filename}")
        # Отправляем через Telethon
        return await client.send_file(data.phone, file_stream, caption=data.text)


    async def send_message_bot(bot_token: str, conversation_id: str, text: str):
        log.info(f"send_message_bot for {conversation_id}")
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"chat_id": conversation_id, "text": text})
            response.raise_for_status()
            return response.json()

    async def _listen_task(self, conversation_id: str, my_phone: str, peer_phone: str):
        log.info(f"------ TelegramListener._listen_task started for {conversation_id}")
        connection = TelegramConnection(
            conversation_id=conversation_id,
            my_phone=my_phone,
            peer_phone=peer_phone,
            message_callback=_save_and_notify
        )

        log.info(f"------ TelegramListener._listen_task connection {connection}")

        # Сначала подключаемся синхронно
        try:
            await connection.connect()
            log.info(f"---- **---- Connected successfully for {conversation_id}")
            self.clients[conversation_id] = connection.client
            log.info(f"---- **---- Connected successfully self.clients {self.clients}")
        except Exception as e:
            log.error(f"---- **----  Failed to connect for {conversation_id}: {e}")
            return

        log.info(f"------ TelegramListener._listen_task start sync")

        # Потом запускаем ран в фоне
        task = asyncio.create_task(connection.run())

        log.info(f"------ TelegramListener._listen_task start background {task}")

        try:
            await task
        finally:
            if conversation_id in self.clients:
                del self.clients[conversation_id]
            await connection.disconnect()


async def _save_and_notify(db: AsyncSession, conversation_id: str, peer_phone: str, event):
    """Сохраняет сообщение в БД и уведомляет фронт."""
    service = ChatService(db)

    media_id = None
    file_name = None
    mime_type = None

    log.info(f"\n\n - * -+- * -+- * -+ event {event}  \n\n")

    if event.media:
        file_bytes = await event.download_media(bytes)
        media_id = uuid.uuid4()

        # Определяем тип
        if hasattr(event.media, 'document') and event.media.document:
            mime_type = event.media.document.mime_type
            # имя файла можно взять из атрибутов документа
            file_name = None
            if hasattr(event.media.document, 'attributes'):
                for attr in event.media.document.attributes:
                    if hasattr(attr, 'file_name'):
                        file_name = attr.file_name
                        break
            if not file_name:
                file_name = f"file_{media_id}"
        else:
            # фото
            mime_type = "image/jpeg"
            file_name = f"photo_{media_id}.jpg"

        await service._save_file(file_bytes, media_id, file_name, mime_type)

    log.info(f"\n\n - * -+- * -+- * -+ file_name {file_name}  mime_type {mime_type} \n\n")
    try:
        message = await service.save_incoming_message(
            conversation_id=conversation_id,
            peer_phone=peer_phone,
            event=event,
            media_id=media_id,
            file_name=file_name,
            mime_type=mime_type
        )

        await manager.send_new_message(conversation_id, {
            "id": str(message.id),
            "text": message.text,
            "direction": "inbound",
            "created_at": message.created_at.isoformat(),
            "phone": peer_phone,
            "media_id": str(media_id),
            "file_name": file_name,
            "mime_type": mime_type,
            "is_new": True,
        })
    except Exception as e:
        log.error(f"Failed: {e}", exc_info=True)
        raise
