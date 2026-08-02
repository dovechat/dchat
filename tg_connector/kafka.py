from aiokafka import AIOKafkaProducer
import json
import os

from core.config import settings


producer = AIOKafkaProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
)

async def start_kafka():
    await producer.start()


async def stop_kafka():
    await producer.stop()


async def send_event(topic: str, data: dict):
    await producer.send_and_wait(
        topic,
        json.dumps(data, ensure_ascii=False).encode(),
    )