import logging
import httpx
import uuid
from typing import Dict, Optional
from fastapi import Request
from core.database import get_db
from app.repositories.chat_repo import ChatRepository
from app.services.websocket_manager import manager
from models.messages import MessageDirection

log = logging.getLogger(__name__)


class GreenWhatsAppConnection:
    """Соединение с Green API для одной линии"""

    def __init__(self, id_instance: str, api_token: str):
        self.id_instance = id_instance
        self.api_token = api_token

    def api_url(self):
        return f"https://api.green-api.com/waInstance{self.id_instance}"

    def send_text_url(self):
        return f"{self.api_url()}/sendMessage/{self.api_token}"

    def send_file_url(self):
        return f"{self.api_url()}/sendFileByUrl/{self.api_token}"

    async def send(self, url, payload):
        log.info(f"\n\n ************ GreenWhatsAppConnection.send url {url} payload {payload} \n\n")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                log.info(f"\n\n ****** GreenWhatsAppConnection.send response {type(response)} {response} \n\n")
                return response.json()
        except Exception as e:
            log.error(f"!!! --- ERROR: GreenWhatsAppConnection.send failed {e}")

    async def send_message(self, chat_id: str, text: str) -> dict:
        """Отправить сообщение через Green API"""
        url = self.send_text_url()
        payload = {
            "chatId": chat_id,
            "message": text
        }
        return await self.send(url, payload)

    async def send_file(self, chat_id: str, file_url: str, caption: str = "") -> dict:
        """Отправить файл"""
        url = self.send_file_url()
        payload = {
            "chatId": chat_id,
            "urlFile": file_url,
            "fileName": "file",
            "caption": caption
        }
        return await self.send(url, payload)


class GreenWhatsAppListener:
    """Слушатель вебхуков от Green API"""

    def __init__(self):
        self.connections: Dict[str, GreenWhatsAppConnection] = {}
        log.info("GreenWhatsAppListener initialized")

    async def handle_webhook(self, line_id: str, payload: dict):
        """Обработать входящий вебхук от Green API"""
        from app.services.chat_service import ChatService
        event_type = payload.get("typeWebhook")
        log.info(f"Green webhook for line {line_id}, type: {event_type}")

        async for db in get_db():
            chat_service = ChatService(db)
            if event_type == "incomingMessageReceived":
                await self._handle_incoming_message(line_id, payload, chat_service)
            # elif event_type == "outgoingMessageStatus":
            #    await self._handle_message_status(line_id, payload, chat_service)
            else:
                log.warning(f"Unhandled webhook type: {event_type}")


    async def _handle_incoming_message(self, line_id: str, payload: dict, chat_service: "ChatService"):
        """Обработка входящего сообщения"""
        # log.info(f"\n\n --------- _handle_incoming_message payload {payload}")
        message_data = payload.get("messageData", {})
        sender_data = payload.get("senderData", {})

        # Извлекаем номер телефона из chatId (вида 79991234567@c.us)
        chat_id = sender_data.get("chatId", "")
        phone = chat_id.replace("@c.us", "")
        phone = f"+{phone}"

        msg_type = message_data.get("typeMessage")
        file_name, mime_type = None, None
        # log.info(f"\n\n --------- _handle_incoming_message message_data {message_data}")

        media_id = None
        file_url = None
        file_name = None
        mime_type = None

        if msg_type == "textMessage":
            text = message_data.get("textMessageData", {}).get("textMessage")
        if msg_type in ["imageMessage", "videoMessage", "documentMessage", "audioMessage"]:
            media_data = message_data.get("fileMessageData", {})  # всегда fileMessageData
            text = media_data.get("caption", "")
            file_url = media_data.get("downloadUrl")
            mime_type = media_data.get("mimeType")
            media_id = uuid.uuid4()
            file_name_rcv = media_data.get("fileName")
            ext = file_name_rcv.split(".")[1]
            file_name = f"{media_id}.{ext}"

        async for db in get_db():
            self.chat_repo = ChatRepository(db)
            conv = await self.chat_repo.get_conversations_by_phone(line_id, phone, "whatsapp_green")
            # log.info(f"\n\n --------- _handle_incoming_message conv {conv}  phone {phone}  text {text} file_name {file_name}  file_name {file_name} file_url {file_url} \n\n")
            break

        
        # Сохраняем в БД
        message = await chat_service.save_incoming_green(
            conversation_id=conv.id,
            payload=payload,
            media_id=media_id,
            file_name=file_name,
            file_url=file_url,
            mime_type=mime_type,
            text=text,
        )

        ws_message = {
            "id": str(message.id),
            "text": message.text,
            "direction": "inbound",
            "created_at": message.created_at.isoformat(),
            "phone": phone
        }

        if media_id:
            ws_message["media_id"] = str(media_id)
            ws_message["file_name"] = file_name
            ws_message["mime_type"] = mime_type

        # Отправляем через WebSocket
        await manager.send_new_message(conv.id, ws_message)

    '''
    async def _handle_message_status(self, line_id: str, payload: dict, chat_service: ChatService):
        """Обработка статуса доставки"""
        external_id = payload.get("idMessage")
        status = payload.get("status")

        if external_id and status:
            await chat_service.update_message_status(
                external_id=external_id,
                status=status
            )

            # Отправляем статус через WebSocket
            await manager.send_message_status(line_id, {
                "external_id": external_id,
                "status": status
            })
    '''

    async def send_message(self, line_id: str, chat_id: str, text: str) -> dict:
        """Отправить сообщение (вызывается из chat_service)"""
        connection = self.connections.get(line_id)
        if not connection:
            raise ValueError(f"No connection for line {line_id}")

        return await connection.send_message(chat_id, text)


# Глобальный экземпляр слушателя (будет создаваться в main.py)
# green_listener = GreenWhatsAppListener()