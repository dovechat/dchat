import httpx
import json
import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from app.services.websocket_manager import manager
from app.services.chat_service import ChatService
from core.config import settings
from core.database import get_db
from infra.crypto import decrypt
from models.lines import Line
from repo.line_repo import ChannelAccountRepository
from repo.membership_repo import MembershipRepository
from repo.message_repo import MediaRepository
from services.storage_service import StorageService
from app.utils import decrypt_credentials

from core.metrics import webhook_processing_seconds

import logging
log = logging.getLogger("uvicorn.error")

class BotService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.channel_repo = ChannelAccountRepository(db)
        self.conv_repo = ChatRepository(db)
        self.msg_repo = MessageRepository(db)
        self.media_repo = MediaRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.storage = StorageService()

    async def _handle_edited_message(self, line_id: uuid.UUID, line, edited: dict):
        chat = edited.get("chat", {})
        chat_id = chat.get("id")
        message_id = edited.get("message_id")
        text = edited.get("text") or edited.get("caption", "")

        if not chat_id or not message_id:
            log.error("Ignoring invalid edited_message update")
            return {"ok": True}

        conversation, _ = await self.conv_repo.get_or_create_by_chat_id(
            line_id=line_id,
            chat_id=str(chat_id),
            tenant_id=line.tenant_id,
            client_phone=chat.get("username") or str(chat_id),
        )

        messages = await self.msg_repo.get_multi(
            filters={"conversation_id": conversation.id, "channel_msg_id": str(message_id)}
        )
        if not messages:
            log.error(f"_handle_edited_message: message not found chat_id={chat_id} message_id={message_id}")
            return {"ok": True}

        db_message = messages[0]
        await self.msg_repo.update(db_message, text=text)
        await self.db.commit()

        from app.services.websocket_manager import manager
        await manager.send_message_update(str(conversation.id), {
            "type": "edit",
            "message_id": str(db_message.id),
            "text": text,
        })

        return {"ok": True}


    async def handle_webhook(self, line_id: uuid.UUID, update_data: dict, request):
        """Handle incoming update from Telegram Bot API"""
        # Get line and bot token

        # prometheus wrap
        with webhook_processing_seconds.labels(channel_type="telegram_bot", event_type="message").time():
            log.info(f'"request.headers {request.headers}')
            line = await self.db.get(Line, line_id)
            if not line:
                log.error(f"Line {line_id} not found")
                return {"ok": False}
    
            channel_acc = await self.channel_repo.get_by_line_and_type(line_id, "telegram_bot")
            creds = decrypt_credentials(channel_acc.credentials_encrypted)
            secret_token = request.headers.get("x-telegram-bot-api-secret-token")
            log.info(f"\n\n **--**--** creds {creds} n\n ")
            db_secret_token = creds.get("secret_token", "")
            log.info(f"\n\n **--**--** secret_token {secret_token} db_secret_token {db_secret_token} n\n ")
            if secret_token != creds.get("secret_token"):
                log.error(f"!!! -- ERROR --- Invalid Telegram secret_token for line {line_id}")
                raise HTTPException(status_code=403, detail="Bot secure token mismatch")
    
            log.info(f"\n\n ***---** update_data {update_data}")
    
            edited = update_data.get("edited_message")
            if edited:
                return await self._handle_edited_message(line_id, line, edited)
    
            # Extract message data
            message = update_data.get("message", {})
    
            # Extract message data
            message = update_data.get("message", {})
            log.info(f"message {message}")
            chat = message.get("chat", {})
            log.info(f"chat {chat}")
            chat_id = chat.get("id")
            message_id = message.get("message_id")
    
            # Check if it's a valid message
            has_media = any(key in message for key in ["photo", "document", "video", "audio"])
            text = message.get("text") or message.get("caption", "")
    
            if not chat_id or (not text and not has_media):
                log.error("Ignoring non-message update")
                return {"ok": True}
    
            # Find or create conversation
            conversation, is_new = await self.conv_repo.get_or_create_by_chat_id(
                line_id=line_id,
                chat_id=str(chat_id),
                tenant_id=line.tenant_id,
                client_phone=chat.get("username") or str(chat_id),
            )
    
            log.info(f"is_new={is_new} conversation_id={conversation.id} chat_id={chat_id} line_id={line_id}")
    
            # Get bot token from line credentials
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    self.channel_repo {dir(self.channel_repo)}   \n\n ")
            # channel_acc = await self.channel_repo.get_by_line_and_type(line_id, "telegram_bot")
            # log.info(f"\n\n *-**-*-*-*-*-*-*-*   BotService.handle_webhook channel_acc {dir(channel_acc)}   \n\n ")
            # creds = decrypt_credentials(channel_acc.credentials_encrypted)
            bot_token = creds["bot_token"]
            raw_content = update_data
    
            # Process media if present
            media_id = None
            if has_media:
                media_id, file_name, mime_type, raw_content, file_size = await self._process_media_message(
                    message, bot_token, raw_content
                )
    
            db_message = await self.msg_repo.create_message(
                conversation_id=conversation.id,
                direction="inbound",
                text=text,
                channel_msg_id=str(message_id),
                raw_content=raw_content,
                user_id=None
            )
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    db_message {db_message} \n\n ")
            if media_id:
                await self.media_repo.create(message_id=db_message.id, id=media_id, file_name=file_name,
                                             mime_type=mime_type)
                await self.db.flush()
            log.info(f"db_message {db_message.id}")
    
            from app.services.websocket_manager import manager
    
            # 8. Send to WebSocket
            ws_message = {
                "id": str(db_message.id),
                "text": text,
                "direction": "inbound",
                "created_at": db_message.created_at.isoformat(),
                "phone": str(chat_id)
            }
    
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    ws_message {ws_message} \n\n ")
    
            if media_id:
                ws_message["media"] = [{"id": str(media_id), "file_name": file_name, "mime_type": mime_type, "url": self.storage.presigned_url(media_id)}]
    
            if is_new:
                members = await self.membership_repo.get_by_tenant(line.tenant_id)
                for m in members:
                    await manager.send_new_conversation(
                        str(m.user_id),
                        {
                            "id": str(conversation.id),
                            "line_id": str(line_id),
                            "channel_type": "telegram_bot",
                            "client_phone": str(chat_id),
                            "crm_chat_id": str(chat_id),
                        }
                    )
    
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    is_new {is_new} \n\n ")
    
            await manager.send_new_message(str(conversation.id), ws_message)
            log.info(f"send_new_message done")
    
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    crm before \n\n ")
            try:
                from crm.app.services.crm_service import CrmService
                from crm.app.core.uow import CrmUnitOfWork
                crm_uow = CrmUnitOfWork(self.db)
                crm_service = CrmService(crm_uow)
                log.info(f"\n\n *-**-*-*-*-*-*-*-*    before bx_chat_id  \n\n ")
                bx_chat_id = await crm_service.send_to_crm(
                    tenant_id=line.tenant_id,
                    conversation_id=conversation.id,
                    client_phone=str(message.get("from", {}).get("id") or chat_id),
                    client_name=chat.get("first_name") or "",
                    text=text or "",
                    message_id=str(db_message.id),
                    channel_type="telegram_bot",
                    media=[{"id": str(media_id), "file_name": file_name, "mime_type": mime_type, "file_size": file_size}] if media_id else []
                )
                log.info(f"\n\n *-**-*-*-*-*-*-*-*    bx_chat_id {bx_chat_id} \n\n ")
                if bx_chat_id:
                    await self.conv_repo.update(conversation, crm_chat_id=bx_chat_id)
                    log.info(f"\n\n *-**-*-*-*-*-*-*-*  if  bx_chat_id  \n\n ")
            except Exception as e:
                log.error(f"CRM send_to_crm failed: {e}")
    
            log.info(f"\n\n *-**-*-*-*-*-*-*-*    crm after \n\n ")
    
            return {"ok": True}

    async def _process_media_message(
            self, message: dict, bot_token: str, raw_content: dict
    ) -> tuple[str | None, str | None, str | None, dict | None, int | None]:
        """
        Process media from Telegram message, download and save to S3
        Returns: (media_id, file_name, mime_type)
        """
        media_id = None
        file_name = None
        mime_type = None
        file_size = None
        

        chat_service = ChatService(self.db)

        try:
            # Handle photo
            if "photo" in message:
                # Get the largest photo
                photo = message["photo"][-1]
                file_id = photo["file_id"]
                file_name = f"photo_{file_id}.jpg"
                mime_type = "image/jpeg"

                # Get file path from Telegram
                async with httpx.AsyncClient() as client:
                    # Get file info
                    file_info_url = f"{settings.tg_bot_send_url}/bot{bot_token}/getFile"
                    file_info_resp = await client.post(file_info_url, json={"file_id": file_id})
                    file_info = file_info_resp.json()

                    if not file_info.get("ok"):
                        log.error(f"Failed to get file info: {file_info}")
                        return None, None, None, None

                    file_path = file_info["result"]["file_path"]

                    # Download file
                    file_url = f"{settings.tg_bot_send_url}/file/bot{bot_token}/{file_path}"
                    file_resp = await client.get(file_url)
                    file_bytes = file_resp.content
                    file_size = len(file_bytes)

            # Handle document
            elif "document" in message:
                doc = message["document"]
                file_id = doc["file_id"]
                file_name = doc.get("file_name", "document")
                mime_type = doc.get("mime_type", "application/octet-stream")

                # Same download logic as above
                async with httpx.AsyncClient() as client:
                    file_info_url = f"{settings.tg_bot_send_url}/bot{bot_token}/getFile"
                    file_info_resp = await client.post(file_info_url, json={"file_id": file_id})
                    file_info = file_info_resp.json()

                    if not file_info.get("ok"):
                        log.error(f"Failed to get file info: {file_info}")
                        return None, None, None, None

                    file_path = file_info["result"]["file_path"]
                    file_url = f"{settings.tg_bot_send_url}/file/bot{bot_token}/{file_path}"
                    file_resp = await client.get(file_url)
                    file_bytes = file_resp.content
                    file_size = len(file_bytes)

            if file_bytes:
                media_id = str(uuid.uuid4())
                await self.storage.save_file(file_bytes, media_id, file_name, mime_type)

        except Exception as e:
            log.error(f"Error processing media: {e}")
            return None, None, None, None

        if media_id:
            raw_content["file_name"] = file_name
            raw_content["mime_type"] = mime_type

        log.info(f"-------  media_id {media_id}, file_name {file_name}, mime_type {mime_type}, raw_content {raw_content}")
        return media_id, file_name, mime_type, raw_content, file_size


    async def send_message(self, bot_token: str, chat_id: str, text: str):
        """Send message via Telegram Bot API"""
        url = f"{settings.tg_bot_send_url}/bot{bot_token}/sendMessage"
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