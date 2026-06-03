# /mono/chat/app/core/kafka_producer.py
import json
import uuid
from aiokafka import AIOKafkaProducer
from fastapi import UploadFile
from loguru import logger
from core.config import settings
from services.storage_service import StorageService

CHANNEL_TOPICS = {
    "telegram_bot": "telegram_bot_outgoing",
    "telegram_user": "telegram_user_outgoing",
    "vk": "vk_outgoing",
    "waba": "waba_outgoing",
    "whatsapp_green": "whatsapp_green_outgoing",
}


class KafkaEventProducer:
    def __init__(self):
        self.producer = None

    async def start(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            request_timeout_ms=40000,
            retry_backoff_ms=100,
        )
        await self.producer.start()
        logger.info(f"Kafka producer initialized for {settings.kafka_bootstrap_servers}")

    async def send_message(
            self,
            channel_type: str,
            conversation_id: uuid.UUID,
            phone: str,
            text: str,
            user_id: uuid.UUID,
            user_email: str,
            files: list[UploadFile] | None = None,
    ) -> None:
        topic = CHANNEL_TOPICS.get(channel_type)
        if not topic:
            raise ValueError(f"Unknown channel_type: {channel_type}")

        media = []
        if files:
            storage = StorageService()
            for file in files:
                media_id = uuid.uuid4()
                file_bytes = await file.read()
                await storage.save_file(file_bytes, media_id, file.filename, file.content_type)
                logger.info(f"KafkaEventProducer.send_message file saved media_id={media_id}")
                media.append({
                    "id": str(media_id),
                    "file_name": file.filename,
                    "mime_type": file.content_type,
                })

        payload = {
            "conversation_id": str(conversation_id),
            "phone": phone,
            "text": text,
            "media": media,
            "user_id": str(user_id),
            "user_email": user_email,
            "channel_type": channel_type,
        }

        if not self.producer:
            await self.start()

        try:
            await self.producer.send_and_wait(topic=topic, value=payload)
            logger.info(f"KafkaEventProducer.send_message sent topic={topic} conversation_id={conversation_id}")
        except Exception as e:
            logger.error(f"KafkaEventProducer.send_message failed topic={topic}: {e}")
            try:
                await self.producer.stop()
            except Exception:
                pass
            self.producer = None
            raise

    async def close(self):
        if self.producer:
            await self.producer.stop()


kafka_producer = KafkaEventProducer()