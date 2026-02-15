import json
import asyncio
import logging
from aiokafka import AIOKafkaConsumer
from telethon import TelegramClient
from telethon.sessions import StringSession
from core.config import settings
from core.database import get_db
from app.repositories.chat_repo import ChatRepository

log = logging.getLogger(__name__)

_clients: dict = {}


async def get_or_create_client(session_string: str, phone: str) -> TelegramClient:
    if phone in _clients:
        client = _clients[phone]
        if client.is_connected():
            return client

    client = TelegramClient(
        StringSession(session_string),
        int(settings.tg_api_id),
        settings.tg_api_hash
    )
    await client.connect()
    _clients[phone] = client
    return client


async def start_consumer():
    consumer = AIOKafkaConsumer(
        'telegram_outgoing_messages',
        bootstrap_servers='kafka:9092',
        group_id='telegram-sender-group',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest'
    )

    await consumer.start()
    log.info("Telegram consumer started")

    try:
        async for message in consumer:
            data = message.value
            log.info(f"Processing message: {data}")

            async for db in get_db():
                chat_repo = ChatRepository(db)
                session_string = await chat_repo.get_session_by_conversation(data["conversation_id"])
                my_phone = await chat_repo.get_line_phone_by_conversation(data["conversation_id"])
                break

            if not session_string:
                log.error(f"No session for conversation {data['conversation_id']}")
                continue

            try:
                client = await get_or_create_client(session_string, my_phone)
                await client.send_message(data['phone'], data['text'])
                log.info(f"Message sent to {data['phone']}")
            except Exception as e:
                log.error(f"Failed to send: {e}")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_consumer())