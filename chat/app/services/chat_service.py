import asyncio
import base64
import httpx
import json
import uuid

from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from typing import List, Optional, Tuple
from fastapi import Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
from core.redis import rdb
from app.repositories.chat_repo import ChatRepository
from app.repositories.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository, LineRepository
from repo.message_repo import MediaRepository
from repo.tenant_repo import TenantRepository
from app.schemas.chat_schemas import (
    ChannelAvailable,
    ConversationCreate,
    ConversationResponse,
    CrmMessageIn,
    CrmMessageOut,
    LineWithChannelsResponse,
    MessageCreate,
    MessageResponse,
    MessageStatus,
    ConversationListResponse
)
from app.schemas.telegram_schemas import KafkaEvent
from app.senders.factory import SenderFactory
from app.senders.waba import WabaSender
from app.services.websocket_manager import manager
from app.core.kafka_producer import kafka_producer
from core.config import settings
from core.dependencies import get_current_user
from infra.crypto import decrypt
from models.messages import Conversation, Message, MessageDirection
from notification.notification_caller import notify_connection_error
from schemas.auth_schemas import UserContext
from services.storage_service import StorageService

import logging
log = logging.getLogger("uvicorn.error")

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ch_acc_repo = ChannelAccountRepository(db)
        self.conv_repo = ChatRepository(db)
        self.msg_repo = MessageRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.media_repo = MediaRepository(db)
        self.line_repo = LineRepository(db)
        self.storage = StorageService()

    async def _init_sender(
            self,
            channel_type: str,
            conv_id: uuid.UUID,
            tg_listener=None,
    ):
        sender = SenderFactory.get_sender(channel_type)
        if channel_type == "telegram_user":
            sender.set_listener(tg_listener)
            sender.set_conv_id(conv_id)
            return sender
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(conv_id)
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))
        if channel_type == "telegram_bot":
            sender.set_bot_token(creds["bot_token"])
        else:
            sender.set_creds(creds)

        sender.set_line_id(channel_acc.line_id)

        log.info(f"_init_sender channel_type={channel_type} conv_id={conv_id}")
        return sender

    async def _process_queue_outgoing(
            self,
            channel_type: str,
            data: MessageCreate,
            current_user: UserContext,
            tg_listener=None,
    ) -> MessageResponse:
        message = await self.msg_repo.get_by_id(data.message_id)

        conv = await self.conv_repo.get_by_id(data.conversation_id)

        if not data.phone:
            data.phone = conv.client_phone

        if data.media:
            for m in data.media:
                try:
                    await self.media_repo.create(message_id=message.id, **m)
                except Exception:
                    await self.db.rollback()
            await self.db.commit()
            await self.db.refresh(message, attribute_names=["media"])

        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": [{**m, "url": self.storage.presigned_url(m["id"])} for m in (data.media or [])],
        })

        sender = await self._init_sender(channel_type, data.conversation_id, tg_listener)
        result = None
        success = False
        try:
            result = await sender.send(data, self.db)
            success = bool(result)
            log.info(f"_process_queue_outgoing sent channel_type={channel_type} result={result}")
        except Exception as e:
            log.error(f"_process_queue_outgoing send failed channel_type={channel_type}: {e}")
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError)):
                await notify_connection_error(conv.line_id, channel_type, self.db)

        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type=channel_type,
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=sender.extract_msg_id(result),
            raw_content=result if isinstance(result, dict) else None,
        )
        return MessageResponse.model_validate(message)

    async def create_msg_telegram_bot(self, data, files=[], current_user=None):
        return await self._process_queue_outgoing("telegram_bot", data, current_user)

    async def create_msg_telegram_user(self, data, files=[], current_user=None, listener=None):
        return await self._process_queue_outgoing("telegram_user", data, current_user, tg_listener=listener)

    async def create_msg_whatsapp_green(self, data, files=[], current_user=None):
        return await self._process_queue_outgoing("whatsapp_green", data, current_user)

    async def create_msg_waba(self, data, files=[], current_user=None):
        return await self._process_queue_outgoing("waba", data, current_user)

    async def create_msg_vk(self, data, files=[], current_user=None):
        return await self._process_queue_outgoing("vk", data, current_user)

    async def edit_message(self, message_id: uuid.UUID, text: str, current_user: UserContext, tg_listener: 'TelegramListener') -> MessageResponse:
        message = await self.msg_repo.get_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="message not found")
        conv = await self.conv_repo.get_by_id(message.conversation_id)
        if not message.channel_msg_id:
            raise HTTPException(status_code=400, detail="no channel_msg_id")

        sender = await self._init_sender(conv.channel_type, conv.id, tg_listener=tg_listener)
        await sender.edit(message.channel_msg_id, conv.client_phone, text)

        await self.msg_repo.update(message, text=text)
        await self.db.commit()

        await manager.send_message_update(str(conv.id), {
            "type": "edit",
            "message_id": str(message.id),
            "text": text,
        })
        return MessageResponse.model_validate(message)

    async def delete_message(self, message_id: uuid.UUID, current_user: UserContext, tg_listener: 'TelegramListener') -> None:
        message = await self.msg_repo.get_by_id(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="message not found")
        conv = await self.conv_repo.get_by_id(message.conversation_id)
        if not message.channel_msg_id:
            raise HTTPException(status_code=400, detail="no channel_msg_id")

        sender = await self._init_sender(conv.channel_type, conv.id, tg_listener=tg_listener)
        await sender.delete(message.channel_msg_id, conv.client_phone)

        await self.msg_repo.delete(message)
        await self.db.commit()

        await manager.send_message_update(str(conv.id), {
            "type": "delete",
            "message_id": str(message.id),
        })


    async def get_conversations(
            self,
            user_id: uuid.UUID,
            line_id: uuid.UUID | None = None,
            skip: int = 0,
            limit: int = 100
    ) -> List[ConversationListResponse]:
        tenants = await self.tenant_repo.get_all_tenants(user_id=user_id)
        log.info(f"DEBUG tenants: {tenants}")
        tenant_ids = [t.id for t in tenants]
        log.info(f"DEBUG tenant_ids: {tenant_ids}")
        tenant_map = {t.id: t.name for t in tenants}

        if not tenant_ids:
            return []

        rows = await self.conv_repo.get_conversations_with_stats(tenant_ids, skip, limit)

        log.info(f"DEBUG rows: {rows}")

        conversations = []
        for conv, line_name, tenant_id, unread_count, last_msg_at in rows:
            last_msg = None
            if last_msg_at:
                last_msg_obj = await self.msg_repo.get_last_message(conv.id)
                if last_msg_obj:
                    last_msg = MessageResponse.model_validate(last_msg_obj)

            conversations.append(ConversationListResponse(
                **conv.__dict__,
                line_name=line_name,
                tenant_id=tenant_id,
                unread_count=unread_count,
                last_message=last_msg
            ))

        log.info(f"DEBUG conversations: {conversations}")

        return conversations

    async def get_conversations_filtered(
            self,
            user_id: uuid.UUID,
            line_id: uuid.UUID | None = None,
            channel_type: str | None = None,
            is_closed: bool = False,
    ) -> list[ConversationListResponse]:
        tenants = await self.tenant_repo.get_all_tenants(user_id=user_id)
        tenant_ids = [t.id for t in tenants]
        if not tenant_ids:
            return []

        log.info(f"user_id {user_id} line_id {line_id} channel_type {channel_type} is_closed {is_closed}")

        log.info(f"tenant_ids {tenant_ids}")

        rows = await self.conv_repo.get_conversations_with_filters(
            tenant_ids=tenant_ids,
            line_id=line_id,
            channel_type=channel_type,
            is_closed=is_closed,
        )

        log.info(f"rows {rows}")

        conversations = []
        for conv, line_name, tenant_id, unread_count, last_msg_at in rows:
            last_msg = None
            if last_msg_at:
                last_msg_obj = await self.msg_repo.get_last_message(conv.id)
                if last_msg_obj:
                    last_msg = MessageResponse.model_validate(last_msg_obj)
            conversations.append(ConversationListResponse(
                **conv.__dict__,
                line_name=line_name,
                tenant_id=tenant_id,
                unread_count=unread_count,
                last_message=last_msg
            ))
        log.info(f"conversations {conversations}")
        return conversations



    async def get_lines_with_available_channels(self, user_id: uuid.UUID) -> list[LineWithChannelsResponse]:
        tenants = await self.tenant_repo.get_all_tenants(user_id=user_id)
        tenant_map = {t.id: t.name for t in tenants}

        lines: dict[uuid.UUID, LineWithChannelsResponse] = {}
        for tenant in tenants:
            rows = await self.conv_repo.get_lines_with_available_channels(tenant.id)
            for row in rows:
                if row.id not in lines:
                    lines[row.id] = LineWithChannelsResponse(
                        id=row.id,
                        name=row.name,
                        tenant_id=tenant.id,
                        tenant_name=tenant_map[tenant.id],
                        channels=[]
                    )
                lines[row.id].channels.append(ChannelAvailable(channel_type=row.channel_type))

        return list(lines.values())


    async def get_conversation(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID
    ) -> Optional[ConversationResponse]:
        """Get conversation with all messages"""
        conversation = await self.conv_repo.get_conversation_with_messages(conversation_id)

        if not conversation:
            return None

        messages = await self.msg_repo.get_conversation_messages(
            conversation_id, skip=0, limit=1000
        )

        # my_phone = None
        # if conversation.channel_type != "telegram_bot":
        my_phone = await self.conv_repo.get_line_phone_by_conversation(conversation_id)

        log.info(f"\n\n --- ChatService.get_conversation my_phone {my_phone} conversation.__dict__ {conversation.__dict__}--- \n\n ")

        return ConversationResponse(
            **conversation.__dict__,
            messages=[MessageResponse.model_validate(msg) for msg in messages],
            my_phone=my_phone,
        )

    async def get_messages(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100
    ) -> List[MessageResponse]:
        """Get messages for conversation"""
        # Verify access
        conv = await self.conv_repo.get_conversation_with_messages(conversation_id)
        if not conv:
            return []

        messages = await self.msg_repo.get_conversation_messages(
            conversation_id, skip, limit
        )
        messages = list(reversed(messages))
        result = []
        for msg in messages:
            msg_dict = dict(msg.__dict__)
            log.info(f"========  msg.raw_content {msg.raw_content}")
            log.info(f"========  msg.user {msg.user}")
            filename = None
            if msg.raw_content:
                if msg.raw_content.get("file_name") is not None:
                    filename = msg.raw_content.get("file_name")
                if filename is None and msg.raw_content is not None:
                    raw = msg.raw_content or {}
                    filename = (
                        raw.get("messageData", {})
                        .get("fileMessageData", {})
                        .get("fileName")
                    )

            if msg.user:
                msg_dict['user_email'] = msg.user.email
                msg_dict['user_full_name'] = msg.user.full_name
                log.info(f"========  filename {filename}")
            
            log.info(f"========  filename {filename}")
            msg_dict['file_name'] = filename

            media_list = []
            for m in msg.media:
                media_list.append({
                    "id": m.id,
                    "file_name": m.file_name,
                    "mime_type": m.mime_type,
                    "url": self.storage.presigned_url(m.id),
                })
            msg_dict['media'] = media_list

            result.append(MessageResponse.model_validate(msg_dict))
        return result


    async def create_conversation(self, tenant_id, data, tg_listener=None) -> ConversationResponse:
        conversation = await self.conv_repo.create_conversation(
            line_id=data.line_id, channel_type=data.channel_type,
            crm_chat_id=data.crm_chat_id, client_phone=data.client_phone, meta=data.meta
        )

        if data.channel_type == "telegram_user" and tg_listener:
            accs = await self.ch_acc_repo.get_by_line(data.line_id)
            tg_acc = next((a for a in accs if a.channel_type.value == "telegram_user"), None)
            if not tg_acc:
                log.warning(f"create_conversation: no telegram_user ChannelAccount for line={data.line_id}")
            else:
                try:
                    await tg_listener.start_listening(str(conversation.id), tg_acc.phone, data.client_phone or '')
                    log.info(f"create_conversation: start_listening OK conv={conversation.id}")
                except Exception as e:
                    log.error(f"create_conversation: start_listening failed conv={conversation.id}: {e}")

        return ConversationResponse(**conversation.__dict__, messages=[])
    
    
    async def conv_msg(
        self,
        data: MessageCreate,
        current_user: UserContext = Depends(get_current_user),
    ) -> Tuple[Conversation, Message]:
        # Verify conversation exists and belongs to tenant

        cached = await rdb.get(f"conv:{data.conversation_id}")
        if cached:
            conv = SimpleNamespace(**json.loads(cached))
        else:
            conv = await self.conv_repo.get_by_id(data.conversation_id)
            if not conv:
                raise ValueError("Conversation not found")
            await rdb.set(f"conv:{data.conversation_id}", json.dumps({"id": str(conv.id), "is_closed": conv.is_closed}),
                          ex=300)


        # Автооткрытие закрытого чата при новом сообщении
        if conv.is_closed:
            await self.conv_repo.set_conversation_closed(conv.id, False)

        message = await self.msg_repo.create_message(
            user_id=current_user.id if data.direction == MessageDirection.outbound else None,
            conversation_id=data.conversation_id,
            channel_msg_id=data.channel_msg_id,
            direction=data.direction,
            text=data.text,
            raw_content=data.raw_content
        )

        if data.media:
            for m in data.media:
                try:
                    await self.media_repo.create(message_id=message.id, **m)
                except Exception:
                    await self.db.rollback()

        # await self.db.commit()
        # await self.db.refresh(message, attribute_names=["media"])
        log.info(f"conv_msg message.media after refresh: {message.media}")
        return conv, message

    
    async def _finalize_message(
            self,
            message,
            conversation_id: uuid.UUID,
            channel_type: str,
            data: MessageCreate,
            current_user: UserContext,
            success: bool = True,
            channel_msg_id: str = None,
            raw_content: dict = None,
            error: Exception = None,
    ):
        """Общая обработка результата отправки"""
        # 1. Вебсокет о новом сообщении (всегда)
        if success:
            # 2. Обновляем message (channel_msg_id, raw_content)
            if channel_msg_id or raw_content:
                await self.msg_repo.update(
                    message,
                    channel_msg_id=channel_msg_id,
                    raw_content=raw_content
                )
            
            log.info(f"=============== ChatServcie._finalize_message data.raw_content {data.raw_content} data.media {data.media}")

            # 3. Статус delivered
            try:
                log.error(f" ---  _finalize_message manager.send_message_status data.media {data.media}")
                await manager.send_message_status(str(conversation_id), {
                    "message_id": str(message.id),
                    "status": "delivered",
                    # "mime_type": data.raw_content.get("mime_type"),
                    "media": [{**m, "url": self.storage.presigned_url(m["id"])} for m in (data.media or [])],
                })
            except Exception as e:
                log.error(f"!!! ERROR ---  _finalize_message manager.send_message_status data.media {data.media} {e}")


    async def _save_uploaded_file(self, file: UploadFile, media_id: uuid.UUID) -> dict:
        log.info(f"========== ChatService._save_uploaded_file media_id {media_id}")
        file_bytes = await file.read()
        return await self.storage.save_file(file_bytes, media_id, file.filename, file.content_type)


    def clean_raw_content(self, obj):
        """Рекурсивно преобразует все datetime в строки"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return base64.b64encode(obj).decode('ascii')
        elif isinstance(obj, dict):
            return {k: self.clean_raw_content(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.clean_raw_content(i) for i in obj]
        return obj


    async def save_incoming_message(
            self,
            conversation_id: uuid.UUID,
            peer_phone: str,
            event,
            media_id: uuid.UUID = None,
            file_name: str = None,
            mime_type: str = None,
            media_items: list | None = None,
            text: str | None = None,
            channel_msg_id: str | None = None,
    ) -> MessageResponse:
        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text if text is not None else (event.message.text if event.message.text else None),
            channel_msg_id=channel_msg_id or str(event.message.id),
            media=media_items if media_items else (
                [{"id": str(media_id), "file_name": file_name, "mime_type": mime_type}] if media_id else None),
            raw_content={
                "phone": peer_phone,
                "date": event.message.date.isoformat(),
            }
        )
        _, message = await self.conv_msg(data)
        return MessageResponse.model_validate(message)

    async def save_incoming_green(
            self,
            conversation_id: uuid.UUID,
            payload: dict,
            media_id: uuid.UUID | None = None,
            file_name: str | None = None,
            file_url: str | None = None,
            original_file_name: str | None = None,
            mime_type: str | None = None,
            text: str | None = None,
    ) -> MessageResponse:
        """Сохранить входящее сообщение из WhatsApp Green"""

        if file_url:
            async with httpx.AsyncClient() as client:
                res = await client.get(file_url)
                if res:
                    file_bytes = res.content
                    if file_bytes:
                        await self.storage.save_file(file_bytes, media_id, original_file_name or file_name, mime_type)

        raw_content = payload
        if mime_type:
            raw_content["mime_type"] = mime_type

        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text,
            channel_msg_id=payload.get("idMessage"),
            media_id=str(media_id) if media_id else None,
            file_name=original_file_name or file_name,
            mime_type=mime_type,
            raw_content=raw_content
        )

        _, message = await self.conv_msg(data)
        return MessageResponse.model_validate(message)



    async def save_incoming_waba(
            self,
            conversation_id: uuid.UUID,
            external_id: str,
            text: str | None,
            media_items: list | None = None,
            raw_data: dict | None = None
    ) -> MessageResponse:
        """Сохранить входящее сообщение из WABA"""

        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text or "",
            channel_msg_id=external_id,
            media=media_items or [],
            raw_content=raw_data,
        )

        _, message = await self.conv_msg(data, None)
        return MessageResponse.model_validate(message)

    async def save_incoming_vk(
            self,
            conversation_id: uuid.UUID,
            external_id: str,
            text: str | None,
            msg_type: str,
            media_items: list | None = None,
            raw_data: dict | None = None
    ) -> MessageResponse:
        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text or "",
            channel_msg_id=external_id,
            media=media_items,
            raw_content=raw_data
        )
        _, message = await self.conv_msg(data, None)
        return MessageResponse.model_validate(message)

    async def close_or_open_conversation(
        self,
        conversation_id: uuid.UUID,
        is_closed: bool,
        user_id: uuid.UUID,
    ) -> Conversation:
        tenants = await self.tenant_repo.get_all_tenants(user_id=user_id)
        tenant_ids = [t.id for t in tenants]
    
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    
        line = await self.line_repo.get_by_id(conv.line_id)
        if line.tenant_id not in tenant_ids:
            raise HTTPException(status_code=403, detail="Forbidden")
    
        updated = await self.conv_repo.set_conversation_closed(conversation_id, is_closed)
        await self.db.commit()
        return updated

    async def save_crm_incoming(self, data: CrmMessageIn):
        log.info(f" chat_service.save_crm_incoming data {data}")
        conv = await self.conv_repo.get_multi(
            filters={"line_id": data.line_id, "crm_chat_id": data.crm_chat_id},
            limit=1
        )
        log.info(f"chat_service.save_crm_incoming conv {conv} ")
        if not conv:
            return {"status": "not_found"}
        conv = conv[0]
        log.info(f"chat_service.save_crm_incoming conv 2nc {conv} ")

        msg = await self.msg_repo.create(
            conversation_id=conv.id,
            direction=MessageDirection.inbound,
            status=MessageStatus.sent,
            text=data.text,
            raw_content=data.raw_content,
        )

        for m in data.media:
            await self.media_repo.create(
                message_id=msg.id,
                id=uuid.UUID(m["id"]),
                file_name=m["file_name"],
                mime_type=m["mime_type"],
            )

        log.info(f"chat_service.save_crm_incoming msg  {msg} ")
        await manager.send_new_message(str(conv.id), {
            "id": str(msg.id),
            "text": msg.text,
            "direction": "inbound",
            "created_at": msg.created_at.isoformat(),
            "status": "sent",
            "media": [{"id": m["id"], "file_name": m["file_name"], "mime_type": m["mime_type"]} for m in data.media],
        })

        # channel_acc = await self.ch_acc_repo.get_by_line_and_type(conv.line_id, conv.channel_type)
        # creds = decrypt(channel_acc.credentials_encrypted) if channel_acc else None

        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(conv.id)
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))

        if conv.channel_type == "telegram_bot" and creds:
            from app.senders.telegram_bot import TelegramBotSender
            sender = TelegramBotSender()
            sender.set_bot_token(creds["bot_token"])
            await sender.send(MessageCreate(
                conversation_id=conv.id,
                direction=MessageDirection.outbound,
                phone=conv.client_phone,
                text=data.text,
                status=MessageStatus.sent,
                media=data.media
            ))

        return {"status": "ok"}


    async def start_crm_outgoing(self, data: CrmMessageOut) -> dict:
        log.info("start_crm_outgoing")
    
        convs = await self.conv_repo.get_multi(
            filters={"line_id": data.line_id, "client_phone": data.client_phone},
            limit=1,
        )
        if convs:
            log.info("start_crm_outgoing if convs")
            conv = convs[0]
            log.info(f"start_crm_outgoing if convs conv {conv}")
            if conv.crm_chat_id:
                log.info(f"start_crm_outgoing if convs conv.crm_chat_id {conv.crm_chat_id}")
                return {"status": "exists", "conversation_id": str(conv.id)}
        else:
            conv = await self.conv_repo.create(
                line_id=data.line_id,
                client_phone=data.client_phone,
                channel_type=data.channel_type,
                crm_chat_id=f"dc_{data.crm_connection_id}",
            )

        log.info(f"start_crm_outgoing convs {convs}")
        log.info(f"start_crm_outgoing data {data}")

        if data.channel_account_id:
            channel_acc = await self.ch_acc_repo.get_by_id(data.channel_account_id)
        else:
            channel_acc = await self.ch_acc_repo.get_multi(
                filters={"line_id": data.line_id, "channel_type": data.channel_type},
                limit=1,
            )
            channel_acc = channel_acc[0] if channel_acc else None
        if not channel_acc:
            return {"error": "Канал не найден"}

        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))
        channel_type = channel_acc.channel_type.value if hasattr(channel_acc.channel_type,
                                                                 "value") else channel_acc.channel_type

        sender = SenderFactory.get_sender(channel_type)
        if hasattr(sender, "set_bot_token"):
            sender.set_bot_token(creds.get("bot_token"))

        await sender.send(MessageCreate(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            phone=data.client_phone,
            text=data.text,
            status=MessageStatus.sent,
        ))

        log.info(f"start_crm_outgoing creds conv.id {conv.id}")
        return {"status": "ok", "conversation_id": str(conv.id)}

    from app.consumers import TelegramListener
    async def robot_send(self, data: CrmMessageOut, tg_listener: TelegramListener=None) -> dict:
        convs = await self.conv_repo.get_multi(
            filters={"line_id": data.line_id, "client_phone": data.client_phone},
            limit=1,
        )
        if convs:
            conv = convs[0]
        else:
            conv = await self.conv_repo.create(
                line_id=data.line_id,
                client_phone=data.client_phone,
                channel_type=data.channel_type,
                crm_chat_id=f"dc_{data.crm_connection_id}",
            )

        if data.channel_account_id:
            channel_acc = await self.ch_acc_repo.get_by_id(data.channel_account_id)
        else:
            results = await self.ch_acc_repo.get_multi(
                filters={"line_id": data.line_id, "channel_type": data.channel_type},
                limit=1,
            )
            channel_acc = results[0] if results else None
        if not channel_acc:
            return {"error": "Канал не найден"}

        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))
        channel_type = channel_acc.channel_type.value if hasattr(channel_acc.channel_type,
                                                                 "value") else channel_acc.channel_type

        msg = await self.msg_repo.create(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
            text=data.text,
        )

        media = []
        if data.media:
            for m in data.media:
                await self.media_repo.create(
                    message_id=msg.id,
                    id=uuid.UUID(m["id"]),
                    file_name=m["file_name"],
                    mime_type=m["mime_type"],
                )
            media = data.media

        # sender = SenderFactory.get_sender(channel_type)
        sender = await self._init_sender(channel_type, conv.id, tg_listener)
        if hasattr(sender, "set_listener"):
            sender.set_listener(tg_listener)
        if hasattr(sender, "set_bot_token"):
            sender.set_bot_token(creds.get("bot_token"))

        await sender.send(MessageCreate(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            phone=data.client_phone,
            text=data.text,
            status=MessageStatus.sent,
            media=media,
        ))

        return {"status": "ok", "conversation_id": str(conv.id), "message_id": str(msg.id)}