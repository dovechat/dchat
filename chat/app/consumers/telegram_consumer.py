import httpx
import json
import asyncio
import logging
import os
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
    topic = os.getenv('KAFKA_TOPIC', 'telegram_user_retry')
    group_id = os.getenv('KAFKA_GROUP_ID', 'telegram-retry-group')

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers='kafka:9092',
        group_id=group_id,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest'
    )

    await consumer.start()
    log.info(f"Telegram retry consumer started for topic {topic}")

    try:
        async for message in consumer:
            event_data = message.value
            log.info(f"Processing retry event: {event_data}")

            # Извлекаем вложенные данные
            payload = event_data.get('payload', {})
            conversation_id = payload.get('conversation_id')
            text = payload.get('text')
            phone = event_data.get('account_phone')

            if not conversation_id or not text or not phone:
                log.error(f"Missing required fields in retry event: {event_data}")
                continue

            log.info(f"\n\n ++++++++++ start_consumer payload {payload} \n\n")

            async for db in get_db():
                chat_repo = ChatRepository(db)
                if topic == 'telegram_user_retry':
                    session_string = await chat_repo.get_session_by_conversation(conversation_id)
                    my_phone = await chat_repo.get_line_phone_by_conversation(conversation_id)
                    # отправка через Telethon
                    if not session_string:
                        log.error(f"No session for conversation {conversation_id}")
                        continue
    
                    try:
                        client = await get_or_create_client(session_string, my_phone)
                        await client.send_message(phone, text)
                        log.info(f"Retry message sent to {phone}")
                    except Exception as e:
                        log.error(f"Retry failed: {e}")

                elif topic == 'telegram_bot_retry':
                    channel_acc = await chat_repo.get_channel_acc_by_conversation(conversation_id)
                    if not channel_acc:
                        log.error(f"No bot token for conversation {conversation_id}")
                        continue

                    try:
                        async with httpx.AsyncClient() as client:
                            url = f"https://api.telegram.org/bot{channel_acc.bot_token}/sendMessage"
                            await client.post(
                                url,
                                json={
                                    "chat_id": phone,
                                    "text": text
                                }
                            )
                        log.info(f"Bot retry sent to {phone}")
                    except Exception as e:
                        log.error(f"Bot retry failed: {e}")
                break


    finally:
        await consumer.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_consumer())