import json
import os
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from core.config import settings
from core.database import get_db
from crm.app.services.crm_service import CrmService
from crm.app.core.uow import CrmUnitOfWork
from app.core.uow import ChatUoW
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import MessageCreate, MessageDirection, MessageStatus
from app.consumers.telegram_listener import TelegramListener
from schemas.auth_schemas import UserContext


log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

DLT_TOPIC = "outgoing_dlt"
MAX_RETRIES = 5

async def process_message(
    event_data: dict,
    channel_type: str,
    chat_service: ChatService,
    crm_service: CrmService,
):
    if event_data.get("action") == "edit":
        current_user = UserContext(
            id=uuid.UUID(event_data["user_id"]),
            email=event_data["user_email"],
        )
        await chat_service.edit_outgoing_message(
            event_data["message_id"],
            event_data["text"],
            current_user,
            phone=event_data["phone"],
            line_id=uuid.UUID(event_data["line_id"]),
            channel_type=channel_type,
        )
        return

    if event_data.get("action") == "delete":
        current_user = UserContext(
            id=uuid.UUID(event_data["user_id"]),
            email=event_data["user_email"],
        )
        await chat_service.delete_message(
            event_data["message_id"],
            current_user,
            phone=event_data["phone"],
            line_id=uuid.UUID(event_data["line_id"]),
            channel_type=channel_type,
            crm_service=crm_service,
        )
        return

    media = event_data.get("media", [])
    data = MessageCreate(
        conversation_id=uuid.UUID(event_data["conversation_id"]),
        direction=MessageDirection.outbound,
        phone=event_data["phone"],
        crm_message_id=event_data["crm_message_id"],
        text=event_data["text"],
        status=MessageStatus.sent,
        media=media,
        message_id=event_data.get("message_id"),
        template=event_data.get("template")
    )
    log.info(f"\n\n outgoing_consumer media {media} event_data {event_data}\n\n")
    current_user = UserContext(
        id=uuid.UUID(event_data["user_id"]),
        email=event_data["user_email"],
    )
    handler = getattr(chat_service, settings.CHANNEL_HANDLERS[channel_type])
    kwargs = dict(data=data, files=[], current_user=current_user)
    await handler(**kwargs)


async def start_consumer(group_id: str = "outgoing-consumer-group", topics: list[str] | None = None):
    consumer = AIOKafkaConsumer(
        *(topics or settings.TOPICS),
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
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
            log.info(f"Processing message topic={message.topic} attempt={attempt} event_data={event_data}")

            async with get_session() as db:
                chat_service = ChatService(db)
                crm_uow = CrmUnitOfWork(db)
                crm_service = CrmService(crm_uow)
                
                try:
                    await process_message(event_data, channel_type, chat_service, crm_service)
                    await consumer.commit()
                    log.info(f"Message committed topic={message.topic}")
                except Exception as e:
                    log.error(f"Send failed topic={message.topic}: {e}")
                    event_data["_error"] = str(e)
                    await dlt_producer.send_and_wait(DLT_TOPIC, value=event_data)
                    await consumer.commit()
    finally:
        await consumer.stop()
        await dlt_producer.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    group_id = os.getenv("KAFKA_GROUP_ID", "outgoing-consumer-group")
    topics_env = os.getenv("KAFKA_TOPICS")
    topics = topics_env.split(",") if topics_env else None
    asyncio.run(start_consumer(group_id=group_id, topics=topics))