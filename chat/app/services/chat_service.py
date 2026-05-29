import asyncio
import base64
import httpx
import json
import uuid

from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple
from fastapi import Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
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

        result = []
        for msg in messages:
            msg_dict = msg.__dict__
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
            result.append(MessageResponse.model_validate(msg_dict))
        return result


    async def create_conversation(
            self,
            tenant_id: uuid.UUID,
            data: ConversationCreate
    ) -> ConversationResponse:
        """Create new conversation"""
        conversation = await self.conv_repo.create_conversation(
            line_id=data.line_id,
            channel_type=data.channel_type,
            crm_chat_id=data.crm_chat_id,
            client_phone=data.client_phone,
            meta=data.meta
        )

        return ConversationResponse(
            **conversation.__dict__,
            messages=[]
        )
    
    
    async def conv_msg(
        self,
        data: MessageCreate,
        current_user: UserContext = Depends(get_current_user),
    ) -> Tuple[Conversation, Message]:
        # Verify conversation exists and belongs to tenant
        # log.info(f"+++++ chat_service ChatService.create_message current_user {current_user}")
        # log.info(f"chat_service ChatService.create_message data {data}")
        conv = await self.conv_repo.get_conversation_with_messages(data.conversation_id)
        if not conv:
            raise ValueError("Conversation not found")
        # log.info(f"chat_service ChatService.create_message conv {conv}")

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
                await self.media_repo.create(message_id=message.id, **m)

        await self.db.commit()
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
            
            log.info(f"=============== ChatServcie._finalize_message data.raw_content {data.raw_content}")




            # 3. Статус delivered
            await manager.send_message_status(str(conversation_id), {
                "message_id": str(message.id),
                "status": "delivered",
                "mime_type": data.raw_content.get("mime_type")
            })
        else:
            # 4. Ошибка -> в Kafka (для каждого канала своё)
            topic_map = {
                "telegram_user": "telegram-user-retry",
                "telegram_bot": "telegram-bot-retry",
                "whatsapp_green": "whatsapp-green-retry",
                "waba": "waba-retry",
                "vk": "vk-retry",
            }

            log.info(f"=============== !!! FAIL success {success} ChatServcie._finalize_message")

            topic = topic_map.get(channel_type, "default_retry")

            log.info(f"=============== !!! FAIL === success {success} ChatServcie._finalize_message topic {topic}")

            try:
                await kafka_producer.send_event(
                    topic=topic,
                    event=KafkaEvent(
                        event_id=str(uuid.uuid4()),
                        event_type='message_retry',
                        payload={
                            'message_id': str(data.id),
                            'conversation_id': str(conversation_id),
                            'text': data.text,
                            # edia_id': data.media_id  # если есть
                        },
                        account_phone=data.phone
                    )
                )
                log.info(f"\n\n !!!  ------- KAFKA send_event  ---------- data.text {data.text} conversation_id {conversation_id} \n\n")
            except Exception as e:
                log.error(f"\n\n !!! ERROR ------- kafka send_event failed: {e} ---------- \n\n")

    async def _save_uploaded_file(self, file: UploadFile, media_id: uuid.UUID) -> dict:
        log.info(f"========== ChatService._save_uploaded_file media_id {media_id}")
        file_bytes = await file.read()
        return await self.storage.save_file(file_bytes, media_id, file.filename, file.content_type)

    '''
    async def _save_file(self, file_bytes: bytes, media_id: uuid.UUID, filename: str, mime_type: str ) -> dict:
        stream = BytesIO(file_bytes)
        if file_bytes is None:
            return
        size = len(file_bytes)
        metadata = {
            "filename": filename,
            "content_type": mime_type,
            "size": size
        }
        self.s3_client.put_object(
            settings.s3_bucket,  # bucket_name
            str(media_id),  # object_name
            stream,  # data
            size,  # length
            content_type=mime_type,
            metadata=metadata,
        )

        log.info(f"========== _save_file saved media_id {media_id} filename {filename} size {size}")

        return {
            "media_id": media_id,
            "filename": filename,
            "mime_type": mime_type,
            "size": size
        }
    '''

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


    async def create_msg_tguser(
        self,
        request: Request,
        data: MessageCreate,
        files: list[UploadFile] = [],
        current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new message in conversation"""
        listener = request.app.state.listener

        if files:
            media_items = []
            for file in files:
                media_id = uuid.uuid4()
                await self._save_uploaded_file(file, media_id)
                media_items.append({
                    "id": str(media_id),
                    "file_name": file.filename,
                    "mime_type": file.content_type,
                })
            data.media = media_items

        conv, message = await self.conv_msg(data, current_user)

        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": data.media or [],
        })

        sender = SenderFactory.get_sender("telegram_user")
        sender.set_listener(listener)
        # log.info(f"---------- sender {sender}")
        # log.info(f"---------- sender.listener {sender.listener}")
        # log.info(f"---------- sender.listener.send_message_user {sender.listener.send_message_user}")
        sent = None
        try:
            # log.info(f"\n\n +++++++++++++ ChatService.create_msg_tguser  data {data} message {message}  \n\n")
            sent = await sender.send(data)
            success = True if sent else False
            log.info(f"\n\n !!! --- ChatService.create_msg_tguser file sent {sent} file {file} success {success} \n\n")

        except Exception as e:
            log.error(f"ERROR: create_msg_tguser sender.send {e} data {data}")
            success = False
        finally:
            raw_content = None
            if sent:
                raw_content = sent.to_dict()
                raw_content = self.clean_raw_content(raw_content)

            await self._finalize_message(
                message=message,
                conversation_id=data.conversation_id,
                channel_type="telegram_user",
                data=data,
                current_user=current_user,
                success=success,
                channel_msg_id=str(sent.id) if sent else None,
                raw_content=raw_content
            )

        res = MessageResponse.model_validate(message)
        log.info(f"\n\n ++ ChatService.create_msg_tguser data {data}  \n\n")
        # log.info(f"\n\n ++ ChatService.create_msg_tguser message.raw_content {res.raw_content}  \n\n")
        # log.info(f"\n\n ++ ChatService.create_msg_tguser file_name {res.raw_content.get('file_name')}  \n\n")

        return res

    async def create_msg_tgbot(
            self,
            request: Request,
            data: MessageCreate,
            files: list[UploadFile] = [],
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        log.info(f"\n\n *********** create_msg_tgbot  data {data} \n\n")

        if files:
            media_items = []
            for file in files:
                media_id = uuid.uuid4()
                await self._save_uploaded_file(file, media_id)
                media_items.append({
                    "id": str(media_id),
                    "file_name": file.filename,
                    "mime_type": file.content_type,
                })
            data.media = media_items

        # Сохраняем сообщение в БД
        _, message = await self.conv_msg(data, current_user)

        # Первый пинок (новое сообщение)
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": data.media or [],
        })

        log.info(f"\n\n --- ChatServiceChatService.create_msg_tgbot channel_acc before con_id {data.conversation_id} --- \n\n")
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        if channel_acc:
            log.info(f"\n\n --- ChatServiceChatService.create_msg_tgbot channel_acc {channel_acc.__dict__} --- \n\n")
            log.info(f"\n\n --- ChatServiceChatService.create_msg_tgbot channel_acc.credentials_encrypted {channel_acc.credentials_encrypted} --- \n\n")
        else:
            return
        creds_enc = channel_acc.credentials_encrypted.get("encrypted_data")
        creds_str = decrypt(creds_enc)
        bot_token = json.loads(creds_str)["bot_token"]

        # Получаем сендер
        sender = SenderFactory.get_sender("telegram_bot")
        sender.set_bot_token(bot_token)

        try:
            # Отправка через сендер
            result = await sender.send(data)
            channel_msg_id = str(result.get("message_id")) if result else None
            raw_content = result if result else None
            success = True if result else False
        except Exception as e:
            log.error(f"Send failed: {e}")
            success = False
            channel_msg_id = None
            raw_content = None

        # Финальная обработка
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="telegram_bot",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content=raw_content
        )

        return MessageResponse.model_validate(message)

    async def create_msg_whatsapp_green(
            self,
            data: MessageCreate,
            files: list[UploadFile] | None = None,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new WhatsApp Green message"""
        # Получаем креды линии
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        log.info(f"\n\n ************ ChatService.create_msg_whatsapp_green channel_acc {channel_acc} \n\n")
        log.info(f"\n\n ************ ChatService.create_msg_whatsapp_green channel_acc.credentials_encrypted {channel_acc.credentials_encrypted['encrypted_data']} \n\n")
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))

        log.info(f"\n\n ************ ChatService.create_msg_whatsapp_green creds {creds} \n\n")

        # Сохраняем сообщение в БД
        conv, message = await self.conv_msg(data, current_user)

        # Отправляем на фронт сразу
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": data.media or [],
        })

        # Отправка через Green API
        sender = SenderFactory.get_sender("whatsapp_green")
        sender.set_creds(creds)
        success = False

        channel_msg_id = None
        file_info = None
        log.info(f"\n\n --- MEDIA save start \n\n")
        log.info(f"\n\n --- MEDIA save start files length {len(files)} \n\n")
        log.info(f"\n\n --- MEDIA save start files data.media {data.media} \n\n")
        try:
            for i, f in enumerate(files):
                log.info(f"\n\n --- MEDIA save i {i} f {f} \n\n")
                media_id = data.media[i]["id"] if data.media and i < len(data.media) else None
                log.info(f"\n\n --- MEDIA save media_id {media_id} \n\n")
                await self._save_uploaded_file(f, media_id)
                log.info(f"\n\n --- MEDIA save media_id {media_id} _save_uploaded_file passed \n\n")
        except Exception as e:
            log.error(f"WhatsApp Green _save_uploaded_file failed: {e}")

        log.info(f"\n\n --- MEDIA save finish \n\n")

        try:
            result = await sender.send(data)
            success = True if result else None
            channel_msg_id = result.get("idMessage")
        except Exception as e:
            log.error(f"WhatsApp Green send failed: {e}")
            
        # Финальное обновление
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="whatsapp_green",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content=None,  # {"file_name": file.filename, "mime_type": file_info['mime_type']} if file and file_info else None
        )

        return MessageResponse.model_validate(message)

    async def create_msg_waba(
            self,
            request: Request,
            data: MessageCreate,
            files: list[UploadFile] | None = None,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new WABA message"""
        # Получаем креды линии
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))

        log.info(f"\n\n ***** ChatService.create_msg_waba creds {creds} \n\n")

        # Сохраняем сообщение в БД
        conv, message = await self.conv_msg(data, current_user)

        # Отправляем на фронт сразу
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",    
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": data.media or [],
        })

        # Отправка через WABA
        sender = SenderFactory.get_sender("waba")
        sender.set_listener(request.app.state.waba_listener)
        sender.set_creds(creds)
        success = False
        channel_msg_id = None

        try:
            if files:
                media_items = []
                for file in files:
                    media_id = uuid.uuid4()
                    await self._save_uploaded_file(file, media_id)
                    media_items.append({
                        "id": str(media_id),
                        "file_name": file.filename,
                        "mime_type": file.content_type,
                    })
                data.media = media_items

            result = await sender.send(data)
            success = True if result else None
            channel_msg_id = result.get("messages", [{}])[0].get("id")
        except Exception as e:
            log.error(f"WABA send failed: {e}")
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError)):
                await notify_connection_error(uuid.UUID(str(conv.line_id)), "waba", self.db)

        # Финальное обновление
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="waba",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content=None
        )

        return MessageResponse.model_validate(message)




    async def create_msg_vk(
            self,
            request: Request,
            data: MessageCreate,
            files: list[UploadFile] | None = None,
            current_user: UserContext = Depends(get_current_user),
    ) -> MessageResponse:
        """Create new VK message"""
        # Получаем креды линии
        channel_acc = await self.conv_repo.get_channel_acc_by_conversation(data.conversation_id)
        creds = json.loads(decrypt(channel_acc.credentials_encrypted["encrypted_data"]))

        log.info(f"***** create_msg_vk files {files} data.media {data.media}")
        log.info(f"\n\n ***** ChatService.create_msg_vk creds {creds} \n\n")

        if files:
            media_items = []
            for file in files:
                media_id = uuid.uuid4()
                await self._save_uploaded_file(file, media_id)
                media_items.append({
                    "id": str(media_id),
                    "file_name": file.filename,
                    "mime_type": file.content_type,
                })
            data.media = media_items

        # Сохраняем сообщение в БД
        conv, message = await self.conv_msg(data, current_user)

        # Отправляем на фронт сразу
        await manager.send_new_message(str(data.conversation_id), {
            "id": str(message.id),
            "text": message.text,
            "direction": "outbound",    
            "created_at": message.created_at.isoformat(),
            "user_id": str(current_user.id),
            "user_email": current_user.email,
            "status": "sent",
            "media": data.media or [],
        })

        data.message_id = message.id
        # Отправка через VK
        sender = SenderFactory.get_sender("vk")
        sender.set_listener(request.app.state.vk_listener)
        sender.set_creds(creds)
        success = False
        channel_msg_id = None

        log.info(f"\n\n ========== create_msg_vk data.message_id  {data.message_id} \n\n")

        try:
            result = await sender.send(data)
            success = True if result else None
            channel_msg_id = str(result) if isinstance(result, int) else result.get("message_id")
        except Exception as e:
            log.error(f"VK send failed: {e}")
            if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError)):
                await notify_connection_error(uuid.UUID(str(conv.line_id)), "vk", self.db)

        # Финальное обновление
        await self._finalize_message(
            message=message,
            conversation_id=data.conversation_id,
            channel_type="vk",
            data=data,
            current_user=current_user,
            success=success,
            channel_msg_id=channel_msg_id,
            raw_content=None
        )

        return MessageResponse.model_validate(message)




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
            msg_type: str,
            media_items: list | None = None,
            raw_data: dict | None = None
    ) -> MessageResponse:
        """Сохранить входящее сообщение из WABA"""

        data = MessageCreate(
            conversation_id=conversation_id,
            direction=MessageDirection.inbound,
            text=text or "",
            channel_msg_id=external_id,
            media=[
                {"id": str(media_id), "file_name": file_name, "mime_type": mime_type}
            ] if media_id else None,
            raw_content=raw_data
        )

        _, message = await self.conv_msg(data, None)  # user_id=None для входящих
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

    '''
    async def upload_file(self, file: UploadFile, media_id: uuid.UUID) -> dict:
        """Upload file to S3"""
        # 1. Читаем файл
        content = await file.read()
    
        # 2. Генерируем метаданные
        metadata = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content)
        }
    
        # 3. Сохраняем в S3 под ключом = media_id
        await self.s3_client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=str(media_id),
            Body=content,
            Metadata=metadata,
            ContentType=file.content_type
        )
    
        # 4. Возвращаем информацию
        return {
            "media_id": media_id,
            "filename": file.filename,
            "mime_type": file.content_type,
            "size": len(content)
        }
    '''

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
            filters={"line_id": data.line_id, "crm_chat_id": data.crm_chat_id, "channel_type": data.channel_type},
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

    async def robot_send(self, data: CrmMessageOut) -> dict:
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

        sender = SenderFactory.get_sender(channel_type)
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