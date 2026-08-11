import logging
import httpx
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
from core.config import settings
from core.database import get_db
from core.metrics import webhook_processing_seconds, webhook_errors_total
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository
from app.services.websocket_manager import manager
from models.messages import MessageDirection
from notification.notification_caller import notify_connection_error


log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

class GreenWhatsAppConnection:
    """Соединение с Green API для одной линии"""

    def __init__(self, id_instance: str, api_token: str, line_id=None, db: AsyncSession =None,):
        self.id_instance = id_instance
        self.api_token = api_token
        self.line_id = line_id
        self.db = db

    def api_url(self):
        return f"{settings.proxy_green_url}/waInstance{self.id_instance}"

    def media_url(self):
        return f"{settings.proxy_green_url}/waInstance{self.id_instance}"

    def send_text_url(self):
        return f"{self.api_url()}/sendMessage/{self.api_token}"

    def send_file_url(self):
        return f"{self.media_url()}/sendFileByUrl/{self.api_token}"

    async def send(self, url, payload):
        log.info(f"\n\n ************ GreenWhatsAppConnection.send url {url} payload {payload} \n\n")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                log.info(f"\n\n ****** GreenWhatsAppConnection.send response {type(response)} {response} \n\n")
                log.info(f"GreenWhatsAppConnection.send response body: {response.text}")
                return response.json()
        except Exception as e:
            log.error(f"!!! --- ERROR: GreenWhatsAppConnection.send failed {e}")
            try:
                await notify_connection_error(self.line_id, channel_type="whatsapp_green", db=self.db)
            except Exception as ne:
                log.error(f"notify_connection_error failed: {ne}")


    async def send_message(self, chat_id: str, text: str) -> dict:
        """Отправить сообщение через Green API"""
        url = self.send_text_url()
        payload = {
            "chatId": chat_id,
            "message": text
        }
        return await self.send(url, payload)

    async def send_file(self, chat_id: str, file_url: str, caption: str = "", file_name: str = "file") -> dict:
        """Отправить файл"""
        url = self.send_file_url()
        payload = {
            "chatId": chat_id,
            "urlFile": file_url,
            "fileName": file_name,
            "caption": caption
        }
        log.info(f"send_file url={url} file_url={file_url} chat_id={chat_id}")
        return await self.send(url, payload)

    def edit_message_url(self):
        return f"{self.api_url()}/editMessage/{self.api_token}"
    
    def delete_message_url(self):
        return f"{self.api_url()}/deleteMessage/{self.api_token}"
    
    async def edit_message(self, chat_id: str, id_message: str, text: str) -> dict:
        url = self.edit_message_url()
        payload = {
            "chatId": chat_id,
            "idMessage": id_message,
            "message": text
        }
        return await self.send(url, payload)
    
    async def delete_message(self, chat_id: str, id_message: str) -> dict:
        url = self.delete_message_url()
        payload = {
            "chatId": chat_id,
            "idMessage": id_message,
            "onlySenderDelete": False
        }
        return await self.send(url, payload)


class GreenWhatsAppListener:
    """Слушатель вебхуков от Green API"""

    def __init__(self):
        self.connections: Dict[str, GreenWhatsAppConnection] = {}
        log.info("GreenWhatsAppListener initialized")

    from core.metrics import prometheus_metrics

    @prometheus_metrics("whatsapp_green")
    async def handle_webhook(self, line_id: str, payload: dict, token):
            """Обработать входящий вебхук от Green API"""
            from app.services.chat_service import ChatService
            log.info(f"\n\n --- **** --- \n token {token}   {settings.green_api_token} \n --- **** --- \n\n")
            if token != settings.green_api_token:
                msg = "Green webhook auth token mismatch"
                log.error(f"!!! -- ERROR -- {msg}")
                return
            else:
                log.info(
                    f"\n\n --- **** --- \n token {token} is equal to  {settings.green_api_token} and authentication has been passed \n --- **** --- \n\n")
    
            event_type = payload.get("typeWebhook")
            log.info(f"Green webhook for line {line_id}, type: {event_type}")
    
            # !!! ----  remove after wa queue will stop to spam ---- !!!
            # if event_type != "incomingMessageReceived":
            #    return
    
            if event_type == "incomingMessageReceived":
                async with get_session() as db:
                    log.info(f"--- get session db {db}")
                    chat_service = ChatService(db)
                    await self._handle_incoming_message(line_id, payload, chat_service, db)
            elif event_type == "outgoingMessageStatus":
                await self._handle_message_status(line_id, payload)
            elif event_type == "stateInstanceChanged":
                await self._handle_instance_state(line_id, payload)
            else:
                log.warning(f"Unhandled webhook type: {event_type}")

    async def _handle_incoming_message(self, line_id: str, payload: dict, chat_service: "ChatService", db: AsyncSession):
        """Обработка входящего сообщения"""
        log.info(f"\n\n --------- _handle_incoming_message payload {payload}")
        message_data = payload.get("messageData", {})
        sender_data = payload.get("senderData", {})

        # Извлекаем номер телефона из chatId (вида 79991234567@c.us)
        chat_id = sender_data.get("chatId", "")
        phone = chat_id.replace("@c.us", "")
        phone = f"+{phone}"

        msg_type = message_data.get("typeMessage")

        media_id = None
        file_url = None
        file_name = None
        mime_type = None
        original_file_name = None

        log.info(f"\n\n --------- msg_type  {msg_type}")

        text = None
        if msg_type == "editedMessage":
            edited_data = message_data.get("editedMessageData", {})
            stanza_id = edited_data.get("stanzaId")
            id_message = edited_data.get("idMessage")
            new_text = edited_data.get("textMessage")
            text = new_text
            msg_repo = MessageRepository(db)
            message = await msg_repo.get_message_by_channel_msg_id(stanza_id)

            log.info(f"edit lookup id_message={stanza_id} found={message}")

            if message:
                await msg_repo.update(message, text=new_text)
                await manager.send_message_update(str(message.conversation_id), {
                    "type": "edit",
                    "message_id": str(message.id),
                    "text": new_text,
                })
                
                try:
                    from crm.app.services.crm_service import CrmService
                    from crm.app.core.uow import CrmUnitOfWork
                    crm_uow = CrmUnitOfWork(db)
                    crm_service = CrmService(crm_uow)
                    line = await crm_uow.lines.get_by_id(line_id)
                    await crm_service.edit_to_crm(
                        tenant_id=line.tenant_id,
                        conversation_id=message.conversation_id,
                        message_id=str(message.id),
                        text=new_text,
                        channel_type="whatsapp_green",
                    )
                except Exception as e:
                    log.error(f"CRM edit_to_crm failed: {e}")

            log.info(f"\n\n ---------  EDIT text {text}  message {message.__dict__} \n\n")
            return

        log.info(f"\n\n ---------  AFTER EDIT \n\n")

        conv = await chat_service.conv_repo.get_conversations_by_phone(line_id, phone, "whatsapp_green")

        if msg_type == "deletedMessage":
            stanza_id = message_data.get("deletedMessageData", {}).get("stanzaId")
            if stanza_id:
                msg_repo = MessageRepository(db)
                message = await msg_repo.get_message_by_channel_msg_id(stanza_id)
                if message:
                    crm_message_id = (message.raw_content or {}).get("crm_message_id")
                    conversation_id = message.conversation_id
                    if not conversation_id:
                        conversation_id = conv.id
                    message_id_local = message.id

                    await msg_repo.delete(message)
                    await manager.send_message_update(str(conversation_id), {
                        "type": "delete",
                        "message_id": str(message_id_local),
                    })

                    if crm_message_id:
                        try:
                            from crm.app.services.crm_service import CrmService
                            from crm.app.core.uow import CrmUnitOfWork
                            crm_uow = CrmUnitOfWork(db)
                            crm_service = CrmService(crm_uow)
                            line = await crm_uow.lines.get_by_id(line_id)
                            await crm_service.delete_from_crm(
                                tenant_id=line.tenant_id,
                                conversation_id=conversation_id,
                                client_phone="",
                                message_id=str(crm_message_id),
                                channel_type="whatsapp_green",
                            )
                        except Exception as e:
                            log.error(f"CRM delete_from_crm failed: {e}")
            return

        if msg_type == "textMessage":
            log.info(f"\n\n --- msg_type == textMessage message_data {message_data}\n\n")
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
            original_file_name = file_name_rcv

        log.info(f"\n\n --------- _handle_incoming_message conv {conv}  phone {phone}  text {text} line_id {line_id} file_name {file_name}  file_name {file_name} file_url {file_url} \n\n")
        if conv is None:
            return

        # Сохраняем в БД
        try:
            message = await chat_service.save_incoming_green(
                conversation_id=conv.id,
                payload=payload,
                media_id=media_id,
                file_name=file_name,
                file_url=file_url,
                original_file_name=original_file_name,
                mime_type=mime_type,
                text=text,
            )
        except Exception as e:
            log.error(f"\n\n !!! --- ERROR chat_service.save_incoming_green {e}---  \n\n")
            return

        ws_message = {
            "id": str(message.id),
            "text": message.text,
            "direction": "inbound",
            "created_at": message.created_at.isoformat(),
            "phone": phone
        }

        log.info(f"\n\n ----  green wh send_to_crm line_id {line_id} \n\n")

        if media_id:
            ws_message["media"] = [
                {
                    "id": str(media_id),
                    "file_name": original_file_name,
                    "mime_type": mime_type,
                    "url": chat_service.storage.presigned_url(media_id)
                }
            ]

        await manager.send_new_message(conv.id, ws_message)


        try:
            from crm.app.services.crm_service import CrmService
            from crm.app.core.uow import CrmUnitOfWork
            from sqlalchemy.ext.asyncio import AsyncSession
            crm_uow = CrmUnitOfWork(db)
            crm_service = CrmService(crm_uow)
            line = await crm_uow.lines.get_by_id(line_id)
            sender_name = sender_data.get("senderName", "")
            log.info(f"green wh send_to_crm tenant_id {line.tenant_id} conversation_id {conv.id}")

            bx_chat = await crm_service.send_to_crm(
                tenant_id=line.tenant_id,
                conversation_id=conv.id,
                client_phone=phone,
                client_name=sender_name,
                text=text or "",
                message_id=str(message.id),
                channel_type="whatsapp_green",
                media=[{"id": str(media_id), "file_name": original_file_name, "mime_type": mime_type,
                        "file_size": 0}] if media_id else [],
            )
            bx_chat_id = bx_chat[0]
            log.info(f"send_to_crm bx_chat {bx_chat} bx_chat_id={bx_chat_id}")
            if bx_chat_id:
                await chat_service.conv_repo.update(conv, crm_chat_id=bx_chat_id)
        except Exception as e:
            log.error(f"CRM send_to_crm failed: {e}")

    async def _handle_message_status(self, line_id: str, payload: dict):
        external_id = payload.get("idMessage")
        status = payload.get("status")
        log.warning(f"_handle_message_status external_id {external_id}")

        if not external_id or not status:
            log.warning(f"Missing fields in message status: {payload}")
            return

        async with get_session() as db:
            chat_repo = MessageRepository(db)
            msg = await chat_repo.get_message_by_channel_msg_id(external_id)
            log.warning(f"_handle_message_status msg {msg}")
            if status == "failed":
                status = "error"
            if msg:
                await chat_repo.set_message_status(msg.id, status)
                await manager.send_message_status(str(msg.conversation_id), {
                    "message_id": str(msg.id),
                    "status": status
                })

    async def _handle_instance_state(self, line_id: str, payload: dict):
        """Обработка изменения статуса инстанса"""
        log.info("*** GreenWhatsAppListener._handle_instance_state")
        state = payload.get("stateInstance")
        conn_status = state
        error_reason = ''
        if state in ["blocked", "sleepMode", "notAuthorized"]:
            log.info(f"!!! --- ERROR --- GreenWhatsAppListener._handle_instance_state state {state}")
            await notify_connection_error(line_id, "whatsapp_green")
            conn_status = "error" if state == "blocked" else "disconnected"
            error_reason = "account_blocked" if state == "blocked" else "phone_offline"
            log.info(f"*** GreenWhatsAppListener._handle_instance_state end {state} error_reason {error_reason}")
        elif state == "authorized":
            conn_status = "connected"
        elif state == "starting":
            conn_status = "disconnected"
        else:
            return

        log.info(f"*** before get_session line_id={line_id} conn_status={conn_status}")
        async with get_session() as db:
            try:
                repo = ChannelAccountRepository(db)
                await repo.update_connection_status(
                    line_id=line_id,
                    status=conn_status,
                    channel_type="whatsapp_green",
                    connection_error=error_reason
                )
                if conn_status in ("error", "disconnected"):
                    await notify_connection_error(line_id, "whatsapp_green",db)
                log.info(f"*** GreenWhatsAppListener._handle_instance_state end try")
            except Exception as e:
                log.error(f"*** GreenWhatsAppListener._handle_instance_state ERROR: {e}")
                raise


    async def send_message(self, line_id: str, chat_id: str, text: str) -> dict:
        """Отправить сообщение (вызывается из chat_service)"""
        connection = self.connections.get(line_id)
        if not connection:
            log.error(f"\n\n /*/*/*/*/*/ No connection for line {line_id} \n\n")
            raise ValueError(f"No connection for line {line_id}")

        return await connection.send_message(chat_id, text)


# Глобальный экземпляр слушателя (будет создаваться в main.py)
# green_listener = GreenWhatsAppListener()