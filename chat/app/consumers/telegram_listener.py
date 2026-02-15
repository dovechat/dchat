import asyncio
import logging
from typing import Dict
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from core.config import settings
from core.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from app.services.websocket_manager import manager

log = logging.getLogger(__name__)


class TelegramListener:
    def __init__(self):
        # ключ: conversation_id → task
        self.tasks: Dict[str, asyncio.Task] = {}
        self.clients: Dict[str, TelegramClient] = {}

    async def start_listening(
        self,
        conversation_id: str,
        my_phone: str,
        peer_phone: str
    ):
        # Если уже слушаем этот диалог — не дублируем
        if conversation_id in self.tasks:
            task = self.tasks[conversation_id]
            if not task.done():
                log.info(f"Already listening for {conversation_id}")
                return
            # Задача упала — убираем и перезапускаем
            del self.tasks[conversation_id]

        task = asyncio.create_task(
            self._listen_task(conversation_id, my_phone, peer_phone),
            name=f"listener_{conversation_id}"
        )
        self.tasks[conversation_id] = task
        log.info(f"Started listening: conversation={conversation_id} my={my_phone} peer={peer_phone}")

    async def stop_listening(self, conversation_id: str):
        task = self.tasks.pop(conversation_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info(f"Stopped listening for {conversation_id}")


    async def send_message(self, conversation_id: str, recipient: str, text: str):
        client = self.clients.get(conversation_id)
        if not client:
            log.error(f"No client for {conversation_id}")
            return
        await client.send_message(recipient, text)
        log.info(f"Sent message to {recipient}")

    async def _listen_task(
        self,
        conversation_id: str,
        my_phone: str,
        peer_phone: str
    ):
        # Получаем сессию из БД
        async for db in get_db():
            chat_repo = ChatRepository(db)
            session_string = await chat_repo.get_session_by_phone(my_phone)
            break  # get_db — генератор, нам нужна одна сессия

        log.info(f"session_string  for phone={my_phone} {session_string}")

        log.info(f"Session length: {len(session_string) if session_string else 0}")
        log.info(f"Session start: {session_string[:20] if session_string else 'NONE'}")


        if not session_string:
            log.error(f"No session found for phone={my_phone}")
            return

        log.info(f"---------- before client -----------")
        log.info(f"API_ID={settings.tg_api_id}, API_HASH={settings.tg_api_hash}")
        client = TelegramClient(
            StringSession(session_string),
            settings.tg_api_id,
            settings.tg_api_hash
        )

        log.info(f"---------- client  for phone={my_phone} {session_string}")

        try:
            log.info(f"Connecting to Telegram for {my_phone}...")
            await client.connect()
            log.info(f"Connected! Checking authorization...")

            log.info(f"Telegram client connected for {my_phone}, listening peer={peer_phone}")
            self.clients[conversation_id] = client
            
            
            if not await client.is_user_authorized():
                log.error(f"Telegram session not authorized for {my_phone}")
                return

            log.info(f"Telegram client connected for {my_phone}, listening peer={peer_phone}")

            @client.on(events.NewMessage)
            async def handler(event):
                if not event.is_private:
                    return

                # Входящее от peer
                if not event.out:
                    sender = await event.get_sender()
                    if not sender:
                        return
                    sender_phone = getattr(sender, 'phone', '') or ''
                    log.info(f"Got incoming from {sender_phone}, expected {peer_phone}")
                    if sender_phone.lstrip('+') != peer_phone.lstrip('+'):
                        log.info(f"Phone mismatch, skipping")
                        return
                    await _save_and_notify(conversation_id, peer_phone, event)

                # Исходящее - написали сами из Telegram
                else:
                    peer = await event.get_chat()
                    peer_phone_out = getattr(peer, 'phone', '') or ''
                    log.info(f"Got outgoing to {peer_phone_out}, expected {peer_phone}")
                    if peer_phone_out.lstrip('+') != peer_phone.lstrip('+'):
                        return
                    await _save_and_notify(conversation_id, peer_phone, event)
            await client.run_until_disconnected()

        except asyncio.CancelledError:
            log.info(f"Listener task cancelled for {conversation_id}")
        except Exception as e:
            log.error(f"Listener error for {conversation_id}: {e}", exc_info=True)
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


async def _save_and_notify(conversation_id: str, peer_phone: str, event):
    """Сохраняет входящее сообщение в БД и уведомляет фронт через WebSocket."""
    message = None
    try:
        async for db in get_db():
            message_repo = MessageRepository(db)
            message = await message_repo.create_message(
                conversation_id=conversation_id,
                direction="inbound",
                text=event.message.text,
                channel_msg_id=str(event.message.id),
                raw_content={
                    "phone": peer_phone,
                    "date": event.message.date.isoformat()
                }
            )
            break  # одна итерация генератора
    except Exception as e:
        log.error(f"Failed to save message for {conversation_id}: {e}", exc_info=True)
        return

    if not message:
        return

    try:
        await manager.send_new_message(conversation_id, {
            "id": str(message.id),
            "text": message.text,
            "direction": "inbound",
            "created_at": message.created_at.isoformat(),
            "phone": peer_phone
        })
    except Exception as e:
        log.error(f"Failed to notify WS for {conversation_id}: {e}", exc_info=True)


listener = TelegramListener()