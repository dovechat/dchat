import asyncio
import httpx
import json
import logging
import os
import socks
import uuid

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Callable, Dict
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
from repo.line_repo import ChannelAccountRepository
from app.schemas.chat_schemas import MessageCreate
from app.services.websocket_manager import manager
from app.services.chat_service import ChatService
from app.utils import get_file_from_s3
from models.messages import MessageDirection
from notification.notification_caller import notify_connection_error
from services.storage_service import StorageService

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

class TelegramConnection:
    def __init__(self, conversation_id: str, my_phone: str, peer_phone: str, message_callback: Callable):
        self.conversation_id = conversation_id
        self.my_phone = my_phone
        self.peer_phone = peer_phone
        self.message_callback = message_callback
        self.client = None
        self._running = False
        self._reconnect_delay = 1
        self._connection_error_notified = False

        log.info(f"TelegramConnection created for {conversation_id}")

    def decrypt(self, enc_data: str) -> dict:
        """Decode  data from encoded strinig to dictionary"""
        # here should be some decoding algorythm
        log.info(f"+++++ telegram_listener decrypt enc_data  {type(enc_data)} {enc_data}")
        return enc_data
        

    async def get_session(self) -> str:
        from infra.crypto import decrypt
        log.info(f"Getting session for {self.my_phone}")
        async with get_session() as db:
            chat_repo = ChatRepository(db)

            log.info(f"-----*--- get_session phone {self.my_phone} conv_id {self.conversation_id}")
            channes_acc = await chat_repo.get_channel_acc_by_conversation(self.conversation_id)

            log.info(f"-------- get_session {self.my_phone} channes_acc  {type(channes_acc.credentials_encrypted)} {channes_acc.credentials_encrypted}")

            creds_enc = json.loads(decrypt(channes_acc.credentials_encrypted["encrypted_data"]))
            log.info(f"-------- session decrypted creds_enc {type(creds_enc)}  {creds_enc}")
            log.info(f"-------- get_session channes_acc {creds_enc} AFTER")

            session = creds_enc["session_string"]
            log.info(f"------ session {session}")
            log.info(f"-------- Session retrieved for {self.my_phone}: {'found' if session else 'not found'}")

        return session


    async def connect(self):
        log.info(f"+++++++++ Connecting to Telegram for {self.conversation_id}")
        session_string = await self.get_session()
        if not session_string:
            raise ValueError(f"No session for {self.my_phone}")

        log.info(f"\n\n +++++++++ Connecting to Telegram settings.tg_proxy_host {settings.tg_proxy_host} settings.tg_proxy_port {settings.tg_proxy_port} \n\n ")

        from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate

        self.client = TelegramClient(
            StringSession(session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(settings.tg_proxy_host, int(settings.tg_proxy_port), settings.tg_proxy_secret),
            auto_reconnect=True,
            connection_retries=5,
            retry_delay=1,
        )

        '''
        self.client = TelegramClient(
            StringSession(session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
            proxy={"proxy_type": socks.SOCKS5, "addr": settings.tg_proxy_host, "port": int(settings.tg_proxy_port)},
            auto_reconnect=True,
            connection_retries=5,
            retry_delay=1
        )
        '''

        log.info(f"+++++++++ Connecting to Telegram self.client {self.client}")

        await self.client.connect()
        await self.client.disconnect()
        await asyncio.sleep(1)
        await self.client.connect()

        await self.client.connect()
        
        log.info(f"+++++++++ Connecting to Telegram self.client after connect")

        if not await self.client.is_user_authorized():
            raise ValueError(f"Not authorized for {self.my_phone}")

        log.info(f"+++++++++ Connecting to Telegram self.client after is_user_authorized")

        @self.client.on(events.NewMessage)
        async def handler(event):
            await self._handle_message(event)

        log.info(f"+++++++++ Connecting to Telegram self.client after @self.client.on")

        self._running = True
        log.info(f"+++++++++ !!! Connected: {self.conversation_id} (client: {self.client is not None})")

        async with get_session() as db:
            line_repo = LineRepository(db)
            chat_repo = ChatRepository(db)
            conv = await chat_repo.get_conv_by_id(self.conversation_id)
            log.info(f"+++++++++ Update connection status in db: conv {conv} {conv.line_id})")
            await line_repo.set_line_status(conv.line_id, {"status": "connected"})
            await db.commit()
            line = await line_repo.get_by_id(conv.line_id)
            self.line_id = conv.line_id
            self.line_name = line.name
            log.info(f"+++++++++ Update connection status in db: after)")

        log.info(f"+++++++++ !!! Connected: after change status")

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
                if not self.client or not self.client.is_connected():
                    log.info(f"Attempting to connect for {self.conversation_id}")
                    await self.connect()
                log.info(f"Running until disconnected for {self.conversation_id}")
                await self.client.run_until_disconnected()
                if not self.client.is_connected():
                    log.error("!!! ERROR --- listener.run Client disconnected unexpectedly")
                    await notify_connection_error(self.line_id, "telegram_user")
                    self._connection_error_notified = True
                    log.error("!!! ERROR --- /end  listener.run Client disconnected unexpectedly")
            except asyncio.CancelledError:
                log.info(f"Run cancelled for {self.conversation_id}")
                break
            except Exception as e:
                log.error(f"Connection error for {self.conversation_id}: {e}")
                await self.disconnect()

                if not self._connection_error_notified:
                    try:
                        await notify_connection_error(self.line_id)
                        self._connection_error_notified = True
                    except Exception as notify_err:
                        log.error(f"!!! notify_connection_error failed: {notify_err}", exc_info=True) 

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
        async with get_session() as db:
            await self.message_callback(db, self.conversation_id, self.peer_phone, event)
        

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
        self._album_buffer: dict[str, list] = {}  # media_group_id -> list of media items
        self._album_tasks: dict[str, asyncio.Task] = {}  # media_group_id -> flush task
        self.storage = StorageService()
        log.info("TelegramListener initialized")

    async def start_listening(self, conversation_id: str, my_phone: str, peer_phone: str):
        log.info(f"******* TelegramListener.start_listening start_listening: conv={conversation_id}, my={my_phone}, peer={peer_phone}")
 
        log.info(f"start_listening called for {conversation_id}")
        if conversation_id in self.tasks:
            task = self.tasks[conversation_id]
            if not task.done():
                client = self.clients.get(conversation_id)
                if client and client.is_connected():
                    log.info(f"Already listening for {conversation_id}")
                    return
                log.info(f"Task alive but client dead for {conversation_id}, cancelling")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.tasks[conversation_id]
                self.clients.pop(conversation_id, None)
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
        log.info(f"*********** TelegramListener.send_message_user data {data}")
        log.info(
            f"*********** TelegramListener.send_message_user self.clients {self.clients} {type(self.clients)} {type(data.conversation_id)}")
        log.info(f"*********** TelegramListener.send_message_user for {data.conversation_id} to {data.phone}")
        conv_id_str = str(data.conversation_id)
        client = self.clients.get(conv_id_str)
        log.info(f"*********** TelegramListener.send_message_user client {client}")

        if not client:
            log.info(f"No client for {data.conversation_id}, trying to restart listener...")

            # Получаем номер линии из БД
            from core.database import get_db
            from app.repositories.chat_repo import ChatRepository
            my_phone = None
           
            conv = None

            async with get_session() as db:
                repo = ChatRepository(db)
                my_phone = await repo.get_line_phone_by_conversation(conv_id_str)
                conv = await repo.get_conv_by_id(conv_id_str)
            '''
            if my_phone:
                await self.start_listening(conv_id_str, my_phone, data.phone)
            else:
                log.error(f"Cannot get my_phone for conversation {data.conversation_id}")
            '''
            await self.start_listening(conv_id_str, my_phone, data.phone)

            # Ждём появления клиента
            for i in range(150):  # увеличил попытки до 60 (6 сек)
                await asyncio.sleep(0.1)
                client = self.clients.get(conv_id_str)
                if client:
                    log.info(f"Client appeared for {data.conversation_id} after {i * 0.1}s")
                    break
            else:
                log.error(f"No client for {data.conversation_id} after waiting")
                try:
                    await notify_connection_error(conv.line_id, "telegram_user")
                    self._connection_error_notified = True
                except Exception as e:
                    log.error(f" \n\n !!! --- ERROR --- cant sent notify_connection_error line_id {conv.line_id} {e}")
                return

        me = await client.get_me()
        log.info(f"TelegramListener Message sending to data.phone {data.phone} from me.phone {me.phone}")
        if not data.phone:
            data.phone = me.phone


        try:
            entity = await client.get_entity(data.phone)
            log.info(
                f"--------------- TelegramListener Entity for {data.phone}: {entity.id} - {getattr(entity, 'phone', 'no phone')}")
            log.info(f"Entity resolved: {type(entity).__name__}")
            log.info(f"------------------- TelegramListener Sending to entity: {entity.id}")
            sent = await client.send_message(entity, data.text)
            log.info(f"TelegramListener Message sent successfully to {data.phone}")
            return sent
        except Exception as e:
            log.error(f"TelegramListener Failed to send message to {data.phone}: {e}", exc_info=True)
            raise

    async def send_file_user(self, data: MessageCreate):
        """Отправить файл из S3 по media_id"""
        log.info(f"------------------- TelegramListener send_file_user start")
        conversation_id = str(data.conversation_id)
        filename = data.raw_content.get("file_name") if data.raw_content else None
        client = self.clients.get(conversation_id)
        
        if not client:
            for i in range(60):
                await asyncio.sleep(0.1)
                client = self.clients.get(conversation_id)
                if client:
                    break
            else:
                log.error(f"No client for {conversation_id} after waiting")
                return

        
        log.info(f'\n\n TelegramListener send_file_user file_name {data.media[0]} \n\n')
        
        sent = None
        if len(data.media) == 1:
            m = data.media[0]
            file_bytes, _ = await get_file_from_s3(m["id"])
            file_stream = BytesIO(file_bytes)
            file_stream.name = m.get("file_name")
            sent = await client.send_file(data.phone, file_stream, caption=data.text)
        else:
            streams = []
            for m in data.media:
                file_bytes, _ = await get_file_from_s3(m["id"])
                file_stream = BytesIO(file_bytes)
                file_stream.name = m.get("file_name")
                streams.append(file_stream)
            sent = await client.send_file(data.phone, streams, caption=data.text)
            if isinstance(sent, list):
                sent = sent[-1]
        log.info(f"------------------- TelegramListener send_file_user start")
        return sent


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
            message_callback=self._save_and_notify
        )

        log.info(f"------ TelegramListener._listen_task connection {connection}")

        # Сначала подключаемся синхронно
        if conversation_id in self.clients and self.clients[conversation_id].is_connected():
            log.info(f"Client already connected for {conversation_id}, reusing")
            connection.client = self.clients[conversation_id]
        else:
            try:
                await connection.connect()
                log.info(f"----**---- Connected successfully for {conversation_id}")
                self.clients[conversation_id] = connection.client
            except Exception as e:
                log.error(f"----**----  Failed to connect for {conversation_id}: {e}")
                return

        log.info(f"------ TelegramListener._listen_task start sync")

        # Потом запускаем ран в фоне
        task = asyncio.create_task(connection.client.run_until_disconnected())

        log.info(f"------ TelegramListener._listen_task start background {task}")

        try:
            await task
        finally:
            if conversation_id in self.clients:
                del self.clients[conversation_id]
            await connection.disconnect()


    async def _save_and_notify(self, db: AsyncSession, conversation_id: str, peer_phone: str, event):
        """Сохраняет сообщение в БД и уведомляет фронт."""
        service = ChatService(db)
    
        media_id = None
        file_name = None
        mime_type = None
    
        if event.media:
            file_bytes = await event.download_media(bytes)
            media_id = uuid.uuid4()
    
            if hasattr(event.media, 'document') and event.media.document:
                mime_type = event.media.document.mime_type
                file_name = None
                if hasattr(event.media.document, 'attributes'):
                    for attr in event.media.document.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                if not file_name:
                    file_name = f"file_{media_id}"
            else:
                mime_type = "image/jpeg"
                file_name = f"photo_{media_id}.jpg"
    
            await self.storage.save_file(file_bytes, media_id, file_name, mime_type)
    
            media_group_id = getattr(event.message, 'grouped_id', None)
            if media_group_id:
                media_group_id = str(media_group_id)
                self._album_buffer.setdefault(media_group_id, []).append({
                    "id": str(media_id),
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "text": event.message.text or "",
                    "channel_msg_id": str(event.message.id),
                    "conversation_id": conversation_id,
                    "peer_phone": peer_phone,
                })
    
                if media_group_id in self._album_tasks:
                    self._album_tasks[media_group_id].cancel()

                self._album_tasks[media_group_id] = asyncio.create_task(
                    self._flush_album(media_group_id, event)
                )
                return
    
        try:
            message = await service.save_incoming_message(
                conversation_id=conversation_id,
                peer_phone=peer_phone,
                event=event,
                media_id=media_id,
                file_name=file_name,
                mime_type=mime_type,
            )
            await manager.send_new_message(conversation_id, {
                "id": str(message.id),
                "text": message.text,
                "direction": "inbound",
                "created_at": message.created_at.isoformat(),
                "phone": peer_phone,
                "media": [{"id": str(media_id), "file_name": file_name, "mime_type": mime_type}] if media_id else [],
                "is_new": True,
            })
        except Exception as e:
            log.error(f"Failed: {e}", exc_info=True)
            raise

        sender = event.message.sender
        client_name = (
            f"{getattr(sender, 'first_name', '') or ''} "
            f"{getattr(sender, 'last_name', '') or ''}"
        ).strip()

        try:
            from crm.app.services.crm_service import CrmService
            from crm.app.core.uow import CrmUnitOfWork
            crm_uow = CrmUnitOfWork(db)
            crm_service = CrmService(crm_uow)
            conv = await service.conv_repo.get_by_id(conversation_id)
            line = await crm_uow.lines.get_by_id(conv.line_id)
            bx_chat_id = await crm_service.send_to_crm(
                tenant_id=line.tenant_id,
                conversation_id=conv.id,
                client_phone=peer_phone,
                client_name=client_name,
                text=event.message.text or "",
                message_id=str(message.id),
                channel_type="telegram_user",
                media=[{"id": str(media_id), "file_name": file_name, "mime_type": mime_type,
                        "file_size": 0}] if media_id else [],
            )
            log.info(f"send_to_crm bx_chat_id={bx_chat_id}")
            if bx_chat_id:
                await service.conv_repo.update(conv, crm_chat_id=bx_chat_id)
        except Exception as e:
            log.error(f"CRM send_to_crm failed: {e}")



    async def _flush_album(self, mgid: str, event):
        await asyncio.sleep(1)
        items = self._album_buffer.pop(mgid, [])
        self._album_tasks.pop(mgid, None)
        if not items:
            return
        first = items[0]
        try:
            async with get_session() as db:
                service = ChatService(db)
                message = await service.save_incoming_message(
                    conversation_id=first["conversation_id"],
                    peer_phone=first["peer_phone"],
                    event=event,
                    media_id=None,
                    file_name=None,
                    mime_type=None,
                    media_items=[{"id": m["id"], "file_name": m["file_name"], "mime_type": m["mime_type"]} for m in items],
                    text=first["text"],
                    channel_msg_id=first["channel_msg_id"],
                )
                await manager.send_new_message(first["conversation_id"], {
                    "id": str(message.id),
                    "text": message.text,
                    "direction": "inbound",
                    "created_at": message.created_at.isoformat(),
                    "phone": first["peer_phone"],
                    "media": [{"id": m["id"], "file_name": m["file_name"], "mime_type": m["mime_type"]} for m in items],
                    "is_new": True,
                })
        except Exception as e:
            log.error(f"Album flush failed: {e}", exc_info=True)