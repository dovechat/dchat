# /mono/chat/app/consumers/outgoing_consumer.py
import json
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from core.config import settings
from core.database import get_db
from app.core.uow import ChatUoW
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import MessageCreate, MessageDirection, MessageStatus
from app.consumers.telegram_listener import TelegramListener
from schemas.auth_schemas import UserContext

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

TOPICS = [
    "telegram_bot_outgoing",
    "telegram_user_outgoing",
    "vk_outgoing",
    "waba_outgoing",
    "whatsapp_green_outgoing",
]

DLT_TOPIC = "outgoing_dlt"
MAX_RETRIES = 5

CHANNEL_HANDLERS = {
    "telegram_bot": "create_msg_tgbot",
    "telegram_user": "create_msg_tguser",
    "vk": "create_msg_vk",
    "waba": "create_msg_waba",
    "whatsapp_green": "create_msg_whatsapp_green",
}


async def process_message(
    event_data: dict,
    channel_type: str,
    chat_service: ChatService,
    tg_listener: TelegramListener,
):
    data = MessageCreate(
        conversation_id=uuid.UUID(event_data["conversation_id"]),
        direction=MessageDirection.outbound,
        phone=event_data["phone"],
        text=event_data["text"],
        status=MessageStatus.sent,
        media=event_data.get("media", []),
    )
    current_user = UserContext(
        id=uuid.UUID(event_data["user_id"]),
        email=event_data["user_email"],
    )
    handler = getattr(chat_service, CHANNEL_HANDLERS[channel_type])
    kwargs = dict(data=data, files=[], current_user=current_user)
    if channel_type == "telegram_user":
        kwargs["listener"] = tg_listener
    await handler(**kwargs)


async def start_consumer():
    tg_listener = TelegramListener()

    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="outgoing-consumer-group",
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=False,
    )
    dlt_producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    )

    while True:
        try:
            await consumer.start()
            await dlt_producer.start()
            log.info("Outgoing consumer started")
            break
        except Exception as e:
            log.error(f"Failed to connect to Kafka, retrying in 5s: {e}")
            await asyncio.sleep(5)

    try:
        async for message in consumer:
            channel_type = message.topic.replace("_outgoing", "")
            event_data = message.value
            attempt = event_data.get("_attempt", 0) + 1
            log.info(f"Processing message topic={message.topic} attempt={attempt} conversation_id={event_data.get('conversation_id')}")

            async with get_session() as db:
                chat_service = ChatService(db)
                try:
                    await process_message(event_data, channel_type, chat_service, tg_listener)
                    await consumer.commit()
                    log.info(f"Message committed topic={message.topic}")
                except Exception as e:
                    log.error(f"Send failed topic={message.topic} attempt={attempt}: {e}")
                    if attempt >= MAX_RETRIES:
                        event_data["_attempt"] = attempt
                        event_data["_error"] = str(e)
                        await dlt_producer.send_and_wait(DLT_TOPIC, value=event_data)
                        log.info(f"Message sent to DLT after {attempt} attempts topic={message.topic}")
                        await consumer.commit()
                    else:
                        event_data["_attempt"] = attempt
                        await asyncio.sleep(2 ** attempt)
    finally:
        await consumer.stop()
        await dlt_producer.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_consumer())