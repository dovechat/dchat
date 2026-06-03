# /mono/chat/app/consumers/dlt_consumer.py
import json
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from core.config import settings
from core.database import get_db
from app.consumers.telegram_listener import TelegramListener
from app.core.uow import ChatUoW
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import MessageCreate, MessageDirection, MessageStatus
from schemas.auth_schemas import UserContext

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

DLT_TOPIC = "outgoing_dlt"
DLT_GROUP_ID = "outgoing-dlt-group"
MAX_RETRIES = 3
RETRY_INTERVAL = 60

CHANNEL_HANDLERS = {
    "telegram_bot": "create_msg_tgbot",
    "telegram_user": "create_msg_tguser",
    "vk": "create_msg_vk",
    "waba": "create_msg_waba",
    "whatsapp_green": "create_msg_whatsapp_green",
}


async def process_dlt_message(
    event_data: dict,
    chat_service: ChatService,
    tg_listener: TelegramListener,
):
    channel_type = event_data.get("channel_type")
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


async def start_dlt_consumer():
    tg_listener = TelegramListener()

    consumer = AIOKafkaConsumer(
        DLT_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=DLT_GROUP_ID,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=False,
    )

    while True:
        try:
            await consumer.start()
            log.info("DLT consumer started")
            break
        except Exception as e:
            log.error(f"Failed to connect to Kafka, retrying in 5s: {e}")
            await asyncio.sleep(5)

    pending = []

    try:
        while True:
            # собираем все что есть в DLT
            try:
                async for message in consumer:
                    pending.append(message)
                    if not await _has_more(consumer):
                        break
            except Exception as e:
                log.error(f"DLT consumer read error: {e}")

            if not pending:
                await asyncio.sleep(RETRY_INTERVAL)
                continue

            log.info(f"DLT consumer processing {len(pending)} messages")
            still_pending = []

            for message in pending:
                event_data = message.value
                attempt = event_data.get("_dlt_attempt", 0) + 1
                event_data["_dlt_attempt"] = attempt
                log.info(f"DLT retry attempt={attempt} conversation_id={event_data.get('conversation_id')}")

                async with get_session() as db:
                    uow = ChatUoW(db)
                    chat_service = ChatService(uow)
                    try:
                        await process_dlt_message(event_data, chat_service, tg_listener)
                        await consumer.commit()
                        log.info(f"DLT message resolved conversation_id={event_data.get('conversation_id')}")
                    except Exception as e:
                        log.error(f"DLT retry failed attempt={attempt}: {e}")
                        if attempt >= MAX_RETRIES:
                            log.error(f"DLT message dropped after {attempt} attempts conversation_id={event_data.get('conversation_id')}")
                            await consumer.commit()
                        else:
                            still_pending.append(message)

            pending = still_pending
            await asyncio.sleep(RETRY_INTERVAL)
    finally:
        await consumer.stop()


async def _has_more(consumer: AIOKafkaConsumer) -> bool:
    try:
        partitions = consumer.assignment()
        for tp in partitions:
            end = await consumer.end_offsets([tp])
            pos = await consumer.position(tp)
            if end[tp] > pos:
                return True
        return False
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_dlt_consumer())