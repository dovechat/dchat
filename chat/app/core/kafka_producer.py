# app/core/kafka_producer.py
import json
from aiokafka import AIOKafkaProducer
from loguru import logger
from core.config import settings
from app.schemas.telegram_schemas import KafkaEvent


class KafkaEventProducer:
    def __init__(self):
        self.producer = None

    async def start(self):
        """Инициализация асинхронного продюсера"""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            request_timeout_ms=40000,
            retry_backoff_ms=100,
        )
        await self.producer.start()
        logger.info(f"Kafka producer initialized for {settings.kafka_bootstrap_servers}")

    async def send_event(self, topic: str, event: KafkaEvent):
        if not self.producer:
            await self.start()

        try:
            event_data = event if isinstance(event, dict) else event.model_dump()
            await self.producer.send_and_wait(topic=topic, value=event_data)
            logger.debug(f"Event sent to {topic}: {event_data.get('event_id')}")
        except Exception as e:
            logger.error(f"\n\n !!! ERROR --- Failed to send event to {topic}: {e} \n\n")
            # сбрасываем продюсер чтобы при следующем вызове пересоздался
            try:
                await self.producer.stop()
            except Exception:
                pass
            self.producer = None
            raise

    async def close(self):
        """Корректное закрытие продюсера"""
        if self.producer:
            await self.producer.stop()


# Создаём глобальный экземпляр
kafka_producer = KafkaEventProducer()