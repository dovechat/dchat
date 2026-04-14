import asyncio
import json
import logging
import signal
from contextlib import asynccontextmanager
from typing import Dict
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from core.config import settings
from core.database import get_db
from app.repositories.chat_repo import ChatRepository

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

class TelegramListenerService:
    def __init__(self):
        self.producer = None
        self.tasks: Dict[str, asyncio.Task] = {}  # conversation_id -> task
        self.shutdown_event = asyncio.Event()

    async def start_listening_for_chat(self, conversation_id: str, phone: str):
        """Запускает прослушивание для конкретного диалога"""
        if conversation_id in self.tasks:
            log.warning(f"Already listening for conversation {conversation_id}")
            return

        task = asyncio.create_task(
            self._listen_chat_task(conversation_id, phone),
            name=f"listener_{conversation_id}"
        )
        self.tasks[conversation_id] = task
        log.info(f"Started listening for conversation {conversation_id}, phone {phone}")

    async def stop_listening_for_chat(self, conversation_id: str):
        """Останавливает прослушивание для диалога"""
        task = self.tasks.pop(conversation_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info(f"Stopped listening for conversation {conversation_id}")

    async def _listen_chat_task(self, conversation_id: str, phone: str):
        """Задача прослушивания одного диалога"""
        session_string = None
        async with get_session() as db:
            chat_repo = ChatRepository(db)
            session_string = await chat_repo.get_session_by_conversation(conversation_id)

        if not session_string:
            log.error(f"No session found for conversation {conversation_id}")
            return

        client = TelegramClient(
            StringSession(session_string),
            int(settings.tg_api_id),
            settings.tg_api_hash
        )

        @client.on(events.NewMessage(incoming=True, from_users=phone))
        async def handler(event):
            await self._handle_incoming_message(conversation_id, phone, event)

        try:
            await client.start()
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            await client.disconnect()
            raise
        except Exception as e:
            log.error(f"Listener task error for {conversation_id}: {e}")
        finally:
            if conversation_id in self.tasks:
                self.tasks.pop(conversation_id, None)

    async def _handle_incoming_message(self, conversation_id: str, phone: str, event):
        """Обработка входящего сообщения"""
        log.info(f"Incoming from {phone}: {event.message.text[:50]}")

        message_data = {
            "conversation_id": conversation_id,
            "phone": phone,
            "text": event.message.text,
            "timestamp": event.message.date.isoformat(),
            "direction": "incoming"
        }

        # Отправляем в Kafka
        await self.producer.send('telegram_incoming_raw', message_data)

    async def _kafka_control_consumer(self):
        """Читает команды управления из Kafka"""
        consumer = AIOKafkaConsumer(
            'telegram_control',
            bootstrap_servers='kafka:9092',
            group_id='telegram-listener-service',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        await consumer.start()
        log.info("Kafka control consumer started")

        try:
            async for message in consumer:
                data = message.value
                action = data.get("action")
                conversation_id = data.get("conversation_id")
                phone = data.get("phone")

                if action == "start":
                    await self.start_listening_for_chat(conversation_id, phone)
                elif action == "stop":
                    await self.stop_listening_for_chat(conversation_id)
                else:
                    log.warning(f"Unknown action: {action}")
        finally:
            await consumer.stop()

    async def start(self):
        """Запуск сервиса"""
        self.producer = AIOKafkaProducer(
            bootstrap_servers='kafka:9092',
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await self.producer.start()

        # Запускаем потребителя команд
        control_task = asyncio.create_task(self._kafka_control_consumer())

        # Ждём сигнала завершения
        await self.shutdown_event.wait()

        # Корректная остановка
        control_task.cancel()
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        await self.producer.stop()

    async def shutdown(self):
        """Инициирует завершение работы"""
        self.shutdown_event.set()

async def main():
    service = TelegramListenerService()

    # Обработка сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(service.shutdown()))

    await service.start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())