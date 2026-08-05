import asyncio
import json
import logging
import uuid
from datetime import datetime

from kafka import send_event
from sqlalchemy import select, and_
from telethon import events

from core.config import settings
from core.database import AsyncSessionLocal
from infra.crypto import decrypt
from models.lines import ChannelAccount, Line, ChannelType, ConnectionStatus, LineStatus
from repo.conversation_repo import ConversationRepository
from messages import (
    serialize_message,
    serialize_edited_message,
    serialize_deleted_message,
)
from tg_client import TelegramClientWrapper


logging.getLogger('telethon').setLevel(logging.DEBUG)
log = logging.getLogger("uvicorn.error")



class ChannelConnection:
    def __init__(self, line_id: str, conversation_id: uuid.UUID | None, phone: str):
        self.line_id = line_id
        self.conversation_id=conversation_id
        self.phone = phone
        self.client: TelegramClientWrapper | None = None
        self.task: asyncio.Task | None = None
        self._reconnect_delay = 1
        self._album_buffer: dict[str, list] = {}
        self._album_tasks: dict[str, asyncio.Task] = {}

    async def _load_session_string(self) -> str:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChannelAccount).where(
                    and_(
                        ChannelAccount.line_id == uuid.UUID(self.line_id),
                        ChannelAccount.channel_type == ChannelType.telegram_user,
                    )
                )
            )
            account = result.scalar_one_or_none()
            if not account:
                raise ValueError(f"No channel_account for line {self.line_id}")
            creds = json.loads(decrypt(account.credentials_encrypted["encrypted_data"]))
            log.info(f"\n\n ---- creds {creds} \n\n")
            return creds["session_string"]

    async def _get_peer_phone(self) -> str:
        async with AsyncSessionLocal() as db:
            conv = await ConversationRepository(db).get_by_line_and_crm(
                uuid.UUID(self.line_id), "telegram_user"
            )
            self._peer_phone_cache = conv.client_phone if conv else ""
        return self._peer_phone_cache

    async def _set_status(self, status: ConnectionStatus, error: str | None = None):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChannelAccount).where(
                    and_(
                        ChannelAccount.line_id == uuid.UUID(self.line_id),
                        ChannelAccount.channel_type == ChannelType.telegram_user,
                    )
                )
            )
            account = result.scalar_one_or_none()
            if account:
                account.connection_status = status
                account.connection_error = error
                account.last_checked_at = datetime.utcnow()

    async def connect(self):
        session_string = await self._load_session_string()

        self.client = TelegramClientWrapper(
            session_string=session_string
        )

        peer_phone = await self._get_peer_phone()

        log.info(f"\n\n[pool] CONNECT LINE id={self.line_id}, peer_phone={peer_phone}\n\n")

        await self.client.connect()

        if not await self.client.is_user_authorized():
            await self._set_status(ConnectionStatus.error, "not authorized")
            raise RuntimeError(f"Session not authorized for line {self.line_id}")

        @self.client.on(events.NewMessage)
        async def _on_new_message(event):
            log.info(f"[pool] NewMessage line={self.line_id} event_id={event.id}")

            media_group_id = getattr(event.message, 'grouped_id', None)
            if media_group_id:
                media_group_id = str(media_group_id)
                media_items = await process_media(event)
                self._album_buffer.setdefault(media_group_id, []).extend(media_items)

                if media_group_id in self._album_tasks:
                    self._album_tasks[media_group_id].cancel()
                self._album_tasks[media_group_id] = asyncio.create_task(
                    self._flush_album(media_group_id, event)
                )
                return

            payload = await serialize_message(
                event, self.line_id, self.conversation_id, peer_phone,
            )
            await send_event("telegram_user_incoming", payload)

        async def _flush_album(self, mgid: str, event):
            await asyncio.sleep(1)
            items = self._album_buffer.pop(mgid, [])
            self._album_tasks.pop(mgid, None)
            if not items:
                return
            payload = await serialize_message(
                event, self.line_id, self.conversation_id, peer_phone,
            )
            payload["message"]["media"] = items
            await send_event("telegram_user_incoming", payload)

        @self.client.on(events.MessageEdited)
        async def _on_edited(event):
            log.info(f"[pool] MessageEdited line={self.line_id} event_id={event.id}")
            await send_event(
                "telegram_user_message_edit",
                serialize_edited_message(
                    event,
                    self.line_id,
                    self.conversation_id,
                ),
            )

        @self.client.on(events.MessageDeleted)
        async def _on_deleted(event):
            log.info(f"\n\n  *** telegram_user_message_delete self.conversation_id {self.conversation_id}\n\n ")
            await send_event(
                "telegram_user_message_delete",
                serialize_deleted_message(
                    event.deleted_ids,
                    self.line_id,
                    self.conversation_id,
                ),
            )

            log.info(f"SEND EVENT DELETE conversation_id {self.conversation_id,}")

        await self._set_status(ConnectionStatus.connected)
        self._reconnect_delay = 1
        log.info(f"[pool] connected line={self.line_id}")

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None

    async def run_forever(self):
        while True:
            try:
                if not self.client or not self.client.is_connected():
                    await self.connect()
                await self.client.run_until_disconnected()
                await self._set_status(ConnectionStatus.disconnected)
            except asyncio.CancelledError:
                break
            except Exception as e:
                error = str(e)

                log.error(f"[pool] connection failed line={self.line_id}: {error}")
                await self._set_status(ConnectionStatus.error, error)
                await self.disconnect()

                if "was used under two different IP addresses" in error:
                    break

                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 300)
        await self.disconnect()


class ConnectionPool:
    def __init__(self):
        self.connections: dict[str, ChannelConnection] = {}
        self._lock = asyncio.Lock()

    async def _eligible_line_ids(self) -> list[tuple[str, str]]:
        """Активные (не disabled/expired) telegram_user каналы, не отключённые вручную."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChannelAccount.line_id, ChannelAccount.phone)
                .join(Line, Line.id == ChannelAccount.line_id)
                .where(
                    ChannelAccount.channel_type == ChannelType.telegram_user,
                    ChannelAccount.connection_status != ConnectionStatus.disconnected,
                    Line.status == LineStatus.active,
                )
            )
            rows = result.all()
            log.info(f"[pool] eligible rows raw: {rows}")
            return [(str(row[0]), row[1] or "") for row in rows]

    def get_client(self, line_id: str) -> TelegramClientWrapper | None:
        conn = self.connections.get(str(line_id))
        if conn and conn.client and conn.client.is_connected():
            return conn.client
        return None

    async def start_channel(self, line_id: str, phone: str):
        line_id = str(line_id)

        async with self._lock:
            existing = self.connections.get(line_id)

            if existing:
                if existing.client and existing.client.is_connected():
                    return "already_connected"

                if existing.task and not existing.task.done():
                    return "starting"

            conversation_id = None
            async with AsyncSessionLocal() as db:
                conv_repo = ConversationRepository(db)
                conversations = await conv_repo.get_multi(
                    filters={
                        "line_id": line_id,
                        "channel_type": "telegram_user",
                    }
                )
                conversation_id = conversations[0].id if conversations else None

            conn = ChannelConnection(line_id, conversation_id, phone)
            self.connections[line_id] = conn
            conn.task = asyncio.create_task(
                conn.run_forever(),
                name=f"tg_conn_{line_id}",
            )

        return "starting"

    async def stop_channel(self, line_id: str):
        line_id = str(line_id)
        conn = self.connections.pop(line_id, None)
        if conn and conn.task and not conn.task.done():
            conn.task.cancel()
            try:
                await conn.task
            except asyncio.CancelledError:
                pass

    async def start_all(self):
        rows = await self._eligible_line_ids()
        log.info(f"\n\n[pool] start_all: {len(rows)} eligible telegram_user channels\n\n")
        for line_id, phone in rows:
            await self.start_channel(line_id, phone)

    async def health_check_loop(self, interval: int | None = None):
        interval = interval or settings.HEALTH_CHECK_INTERVAL
        while True:
            await asyncio.sleep(interval)
            try:
                rows = await self._eligible_line_ids()
                eligible_ids = {line_id for line_id, _ in rows}

                # остановить то, что больше не eligible (отключено руками / disabled / expired)
                for line_id in list(self.connections.keys()):
                    if line_id not in eligible_ids:
                        await self.stop_channel(line_id)

                # поднять то, что eligible, но ещё не в пуле
                for line_id, phone in rows:
                    await self.start_channel(line_id, phone)
            except Exception as e:
                log.error(f"[pool] health_check_loop error: {e}")

    def status(self) -> list[dict]:
        return [
            {
                "line_id": line_id,
                "phone": conn.phone,
                "connected": bool(conn.client and conn.client.is_connected()),
            }
            for line_id, conn in self.connections.items()
        ]

    
    def get_by_phone(self, phone: str) -> TelegramClientWrapper | None:
        for conn in self.connections.values():
            if conn.phone == phone and conn.client:
                return conn.client
    
        return None

pool = ConnectionPool()
