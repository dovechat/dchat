# app/services/bot_service.py

import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from app.services.websocket_manager import manager
from core.database import get_db
from models.lines import Line

import logging
log = logging.getLogger("uvicorn.error")

class BotService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conv_repo = ChatRepository(db)
        self.msg_repo = MessageRepository(db)

    async def handle_webhook(self, line_id: uuid.UUID, update_data: dict):
        """Handle incoming update from Telegram Bot API"""
        # 1. Get line and bot token
        line = await self.db.get(Line, line_id)
        log.info(f"line {line}")
        if not line or line.channel_type != "telegram_bot":
            log.error(f"Line {line_id} not found or not a bot")
            return {"ok": False}

        # 2. Extract message data
        message = update_data.get("message", {})
        log.info(f"message {message}")
        chat = message.get("chat", {})
        log.info(f"chat {chat}")
        chat_id = chat.get("id")
        text = message.get("text", "")
        log.info(f"text {text}")
        message_id = message.get("message_id")
        log.info(f"message_id {message_id}")

        if not chat_id or not text:
            log.error("Ignoring non-message update")
            return {"ok": True}

        # 3. Find or create conversation
        conversation = await self.conv_repo.get_or_create_by_chat_id(
            line_id=line_id,
            chat_id=str(chat_id),
            tenant_id=line.tenant_id,
            client_phone=chat.get("username") or str(chat_id)
        )
        log.info(f"conversation {conversation.id} {conversation.__dict__}")
        # 4. Save message
        db_message = await self.msg_repo.create_message(
            conversation_id=conversation.id,
            direction="inbound",
            text=text,
            channel_msg_id=str(message_id),
            raw_content=update_data,
            user_id=None
        )
        log.info(f"db_message {db_message}")
        # 5. Send to WebSocket
        await manager.send_new_message(str(conversation.id), {
            "id": db_message.id,
            "text": text,
            "direction": "inbound",
            "created_at": db_message.created_at.isoformat(),
            "phone": str(chat_id)
        })
        log.info(f"send_new_message done")
        return {"ok": True}

    async def send_message(self, bot_token: str, chat_id: str, text: str):
        """Send message via Telegram Bot API"""
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text
                }
            )
            response.raise_for_status()
            return response.json()