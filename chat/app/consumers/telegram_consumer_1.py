from aiokafka import AIOKafkaConsumer
from telethon import TelegramClient
from telethon.sessions import StringSession
from core.config import settings
from core.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.consumers.telegram_listener import listener
import json
import asyncio
import logging

log = logging.getLogger(__name__)


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

            await listener.send_message(
                conversation_id=data['conversation_id'],
                recipient=data['phone'],
                text=data['text']
            )
    finally:
        await consumer.stop()
    


    
    try:
        async for message in consumer:
            data = message.value
            log.info(f"Processing message: {data}")

            session_string = None

            async for db in get_db():
                chat_repo = ChatRepository(db)
                session_string = await chat_repo.get_session_by_conversation(data["conversation_id"])
                log.info(f"session_string: {session_string}")
    
            if not session_string:
                logger.error(f"No session found for conversation {conversation_id}")
                return

            log.info(f"session={session_string[:20] if session_string else None}, my_phone={my_phone}")  # ← сюда
    
            await send_telegram_message(
                session_string=session_string,
                recipient=data['phone'],
                message=data['text']
            )
    finally:
        await consumer.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_consumer())