import json
import logging
import uuid
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chat_repo import ChatRepository
from app.services.chat_service import ChatService
from infra.crypto import decrypt
from repo.line_repo import ChannelAccountRepository, InstanceRepository, LineRepository
from schemas.line_schemas import ChannelType


log = logging.getLogger(__name__)

class WebhookHandler(ABC):
    @abstractmethod
    async def handle(self, line_id: str, payload: dict, services: dict):
        pass


class IncomingMessageHandler(WebhookHandler):
    async def handle(self, conv_id: str, payload: dict, services: dict):
        chat_service = services["chat_service"]

        message_data = payload.get("messageData", {})
        sender_data = payload.get("senderData", {})

        chat_id = sender_data.get("chatId", "")
        text = message_data.get("textMessageData", {}).get("textMessage")

        if not text:
            log.warning("Unsupported message type")
            return
    
        log.info(f"****** WebhookService.IncomingMessageHandler.handle conv_id {conv_id} payload {payload}")
    
        message = await chat_service.save_incoming_green(
            conversation_id=conv_id,
            payload=payload
        )
        log.info(f"Message saved: {message.id}")


class MessageStatusHandler(WebhookHandler):
    async def handle(self, line_id: str, payload: dict, services: dict):
        chat_service = services["chat_service"]

        external_id = payload.get("idMessage")
        status = payload.get("status")

        if external_id and status:
            await chat_service.update_message_status(
                external_id=external_id,
                status=status
            )
            log.info(f"Status updated: {external_id} -> {status}")


class StateChangedHandler(WebhookHandler):
    async def handle(self, line_id: str, payload: dict, services: dict):
        channel_repo = services["channel_repo"]

        instance_data = payload.get("instanceData", {})
        wid = instance_data.get("wid", "")
        phone = wid.replace("@c.us", "") if wid else None

        status = payload.get("stateInstance") or payload.get("statusInstance")

        if status == "authorized" and phone:
            # Обновляем статус и номер в channel_accounts
            account = await channel_repo.get_by_line_id(line_id)
            if account:
                await channel_repo.update(
                    account,
                    connection_status="connected",
                    phone=phone,
                    last_checked_at=datetime.now(timezone.utc)
                )
                log.info(f"Line {line_id} authorized, phone: {phone}")


class WebhookHandlerFactory:
    @staticmethod
    def get_handler(event_type: str) -> WebhookHandler | None:
        if event_type == "incomingMessageReceived":
            return IncomingMessageHandler()
        elif event_type == "outgoingMessageStatus":
            return MessageStatusHandler()
        elif event_type in ["stateInstanceChanged", "statusInstanceChanged"]:
            return StateChangedHandler()
        return None


class WebhookService:
    def __init__(self, db: AsyncSession):
        self.channel_repo = ChannelAccountRepository(db)
        self.line_repo=LineRepository(db)
        self.chat_repo = ChatRepository(db)
        self.instance_repo = InstanceRepository(db)
        self.services = {
            "chat_service": ChatService(db),
            "channel_repo":  self.channel_repo,
        }

    async def process_green_webhook(self, payload: dict):
        event_type = payload.get("typeWebhook")
        log.info(f"Green webhook received, type: {event_type}")
        # Получаем номер телефона из payload
        instance_data = payload.get("instanceData", {})
        instance_id = str(instance_data.get("idInstance", ""))

        if not instance_id:
            log.error("Wrong instance_id in webhook")
            return

        sender_data = payload.get("senderData", {})
        chat_id = sender_data.get("chatId", "")
        phone = chat_id.replace("@c.us", "")
        if not phone.startswith("+"):
            phone = f"+{phone}"

        if not chat_id:
            log.error("No chatId in webhook")
            return

        line = await self.instance_repo.get_line_by_instance_id(instance_id)
        if not line:
            log.error(f"Line not found for instance_id {instance_id}")
            return

        line_id = str(line.id)

        # Ищем чат по номеру
        conv = await self.chat_repo.get_conversations_by_phone(line_id, phone, "whatsapp_green")
        log.info(f" \n\n ---------- WebhookService.process_green_webhook conv.id {conv.id} phone {phone} line_id {line_id}  \n\n")

        handler = WebhookHandlerFactory.get_handler(event_type)
        if handler:
            await handler.handle(conv.id, payload, self.services)
        else:
            log.warning(f"Unhandled webhook type: {event_type}")



