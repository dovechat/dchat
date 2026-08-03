import asyncio
import json
import logging
import os

from uuid import UUID
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaConsumer

from airflow.tests.test_cleanup_service import line_id
from core.config import settings
from core.database import get_db
from crm.app.services.crm_service import CrmService
from crm.app.core.uow import CrmUnitOfWork
from app.schemas.telegram_schemas import IncomingEvent, IncomingMessage
from app.services.chat_service import ChatService
from app.services.websocket_manager import manager


log = logging.getLogger(__name__)

get_session = asynccontextmanager(get_db)

async def process_message(
    event_data: dict,
    chat_service: ChatService,
    crm_uow: CrmUnitOfWork,
    crm_service: CrmService,
):
    log.info(f"\n\n process_message event_data {event_data} \n\n")

    line_id_ = event_data.get("line_id", "")
    log.info(f"\n\n process_message line_id_ {type(line_id_)} {line_id_}  \n\n")

    line_id_1 = UUID(line_id_)
    log.info(f"\n\n process_message line_id_1 {type(line_id_1)} {line_id_1}  \n\n")

    conversation_id = (
        UUID(event_data["conversation_id"])
        if event_data.get("conversation_id")
        else None
    )

    log.info(f"\n\n process_message conversation_id {conversation_id} \n\n")

    event_type = event_data.get("event_type")

    if event_type == "message_created":
        event = IncomingEvent(
            message=IncomingMessage(
                **event_data["message"],
            ),
            line_id=line_id_1,
        )

    elif event_type == "message_edit":
        await chat_service.edit_message(
            conversation_id=conversation_id,
            channel_msg_id=str(event_data["message"]["id"]),
            text=event_data["message"].get("text"),
        )
        return


    elif event_type == "message_delete":
        await chat_service.delete_incoming_message(
            conversation_id=conversation_id,
            channel_msg_ids=[str(i) for i in event_data["message_ids"]],
        )

        try:
            messages = await chat_service.msg_repo.get_multi(
                filters={
                    "conversation_id": conversation_id,
                    "channel_msg_id": [str(i) for i in event_data["message_ids"]],
                }
            )
            line = await crm_service._uow.lines.get_by_id(line_id_1)
            for message in messages:
                bx_msg_id = (message.raw_content or {}).get("bx_message_id")
                if not bx_msg_id:
                    continue
                await crm_service.delete_from_crm(
                    tenant_id=line.tenant_id,
                    conversation_id=conversation_id,
                    client_phone="",
                    message_id=str(bx_msg_id),
                    channel_type="telegram_user",
                )
        except Exception as e:
            log.error(f"CRM delete_from_crm failed: {e}")
        return

    log.info(f"\n\n line_id_1 {type(line_id_1)} {line_id_1}  \n\n")

    media = event_data["message"].get("media", [])
    
    log.info(f"\n\n process_message media {media}\n\n")

    message_data = await chat_service.save_incoming_message(
        conversation_id=conversation_id,
        peer_phone=event_data["peer_phone"],
        event=event,
        media_items=media,
    )

    log.info(f"\n\n process_message event_type {event_type}\n\n")
    if event_type == "message_created":
        log.info(f"\n\n process_message event_type IS message_created\n\n")
        try:
            line = await crm_uow.lines.get_by_id(line_id_1)
            log.info(f"send_to_crm line={line}")
            sender = event_data["message"].get("sender") or {}
            log.info(f"send_to_crm sender={sender}")
            bx_chat_id, bx_msg_id = await crm_service.send_to_crm(
                tenant_id=line.tenant_id,
                conversation_id=conversation_id,
                client_phone=event_data["peer_phone"],
                client_name=sender.get("username") or "",
                text=event_data["message"].get("text") or "",
                message_id=str(event_data["message"]["id"]),
                channel_type="telegram_user",
                media=media,
            )
            log.info(f"send_to_crm bx_chat_id={bx_chat_id} bx_msg_id={bx_msg_id}")
            if bx_chat_id:
                await chat_service.conv_repo.update(
                    await chat_service.conv_repo.get_by_id(conversation_id),
                    crm_chat_id=bx_chat_id,
                )
            if bx_msg_id:
                await chat_service.msg_repo.update(
                    message_data,
                    raw_content={"bx_message_id": bx_msg_id},
                )
        except Exception as e:
            log.error(f"CRM send_to_crm failed: {e}")
        log.info(f"\n\n process_message event_type IS message_created after\n\n")

    await manager.send_new_message(
        conversation_id,
        message_data.model_dump(mode="json"),
    )

async def start_consumer(
    group_id: str = "incoming-consumer-group",
    topics: list[str] | None = None,
):
    consumer = AIOKafkaConsumer(
        *(topics or [
            "telegram_user_incoming",
            "telegram_user_message_edit",
            "telegram_user_message_delete",
        ]),
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )

    while True:
        try:
            await consumer.start()
            log.info("Incoming consumer started")
            break
        except Exception as e:
            log.error(
                f"Failed to connect to Kafka, retrying in 5s: {e}"
            )
            await asyncio.sleep(5)

    try:
        async for message in consumer:
            event_data = message.value

            async with get_session() as db:
                chat_service = ChatService(db)
                crm_uow = CrmUnitOfWork(db)
                crm_service = CrmService(crm_uow)

                try:
                    await process_message(
                        event_data,
                        chat_service,
                        crm_uow,
                        crm_service,
                    )

                    await consumer.commit()

                except Exception as e:
                    log.error(
                        f"Incoming message failed: {e}",
                        exc_info=True,
                    )
                    await consumer.commit()

    finally:
        await consumer.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    group_id = os.getenv(
        "KAFKA_GROUP_ID",
        "incoming-consumer-group",
    )

    asyncio.run(
        start_consumer(group_id=group_id)
    )