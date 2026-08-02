import json
from contextlib import asynccontextmanager
from fastapi import HTTPException, WebSocket
from typing import Dict, List
import uuid
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.redis import rdb
from models.lines import ChannelAccount
from models.messages import Conversation
from repo.user import UserRepository

import logging

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.tenant_connections: Dict[str, List[WebSocket]] = {}

    async def connect(
            self,
            websocket: WebSocket,
            conversation_id: str,
            app,
            user_id: str,
            tenant_id: str,
            role: str,
    ) -> None:
        # Проверка доступа
        async with get_session() as db:
            # Загружаем conversation вместе с линией
            stmt = select(Conversation).where(Conversation.id == conversation_id).options(
                selectinload(Conversation.line))
            result = await db.execute(stmt)
            conv = result.scalar_one_or_none()

            if not conv:
                await websocket.close(code=1008, reason="Conversation not found")
                return

            my_phone_stmt = (
                select(ChannelAccount.phone)
                .join(Conversation, and_(
                    Conversation.line_id == ChannelAccount.line_id,
                    Conversation.channel_type == ChannelAccount.channel_type
                ))
                .where(Conversation.id == conversation_id)
            )
            my_phone_result = await db.execute(my_phone_stmt)
            my_phone = my_phone_result.scalar_one_or_none() or ''
            peer_phone = conv.client_phone or ''

            user_repo = UserRepository(db)
            membership = await user_repo.get_membership(
                user_id=uuid.UUID(user_id),
                tenant_id=conv.line.tenant_id
            )
            log.info(f"\n\n ---- membership check user_id={user_id} tenant_id={conv.line.tenant_id} result={membership} \n\n")
            if not membership:
                log.info(f"membership is_active: {membership.is_active}")
                await websocket.close(code=1008, reason="Access denied")
                return

        # Добавляем соединение в список
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        self.active_connections[conversation_id].append(websocket)

        log.info(f"---*----*-- websocket_manager Socket state after append: {websocket.client_state.name}")

        # Если это первое соединение - запускаем listener
        # if len(self.active_connections[conversation_id]) == 1 and conv.channel_type == "telegram_user":
            # listener = app.state.listener
            # log.info(f"+++++++++ websocket_manager ConnectionManager.connect listener.start_listening")
            # await listener.start_listening(conversation_id, my_phone, peer_phone)
            #log.info(f"+++++++++ websocket_manager ConnectionManager.connect listener.start_listening DONE")

        # log.info(f"+++++++ websocket_manager  ConnectionManager.connect Connected: conversation={conversation_id}, total={len(self.active_connections[conversation_id])}")

    async def disconnect(self, conversation_id: str, websocket: WebSocket):
        # listener = websocket.app.state.listener
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
                # await listener.stop_listening(conversation_id)

        log.info(f"Disconnected: conversation={conversation_id}")

    async def send_new_message(self, conversation_id: str, message_data: dict):
        log.info(f"++++++++ websocket manager send_new_message message_data {message_data}")
        conversation_id = str(conversation_id)
        await rdb.publish(f"ws:new_message:{conversation_id}", json.dumps(message_data))

    async def send_message_status(self, conversation_id: str, data: dict):
        conversation_id = str(conversation_id)
        log.info(f"===== WebsocketManager.send_message_status data {data}")
        await rdb.publish(f"ws:message_status:{conversation_id}", json.dumps(data))


    async def connect_tenant(self, websocket: WebSocket, tenant_id: str):
        if tenant_id not in self.tenant_connections:
            self.tenant_connections[tenant_id] = []
        self.tenant_connections[tenant_id].append(websocket)
    
    async def disconnect_tenant(self, tenant_id: str, websocket: WebSocket):
        if tenant_id in self.tenant_connections:
            self.tenant_connections[tenant_id].remove(websocket)
            if not self.tenant_connections[tenant_id]:
                del self.tenant_connections[tenant_id]
    
    async def send_new_conversation(self, tenant_id: str, conversation_data: dict):
        tenant_id = str(tenant_id)
        log.info(f"send_new_conversation tenant_id={tenant_id} connections={list(self.tenant_connections.keys())}")
        if tenant_id in self.tenant_connections:
            for ws in self.tenant_connections[tenant_id][:]:
                try:
                    await ws.send_json({
                        'type': 'new_conversation',
                        'data': conversation_data
                    })
                    log.info(f"send_new_conversation sent to {tenant_id}")
                except Exception as e:
                    log.error(f"send_new_conversation error: {e}")

    async def send_message_update(self, conversation_id: str, data: dict):
        conversation_id = str(conversation_id)
        log.info(f"===== WebsocketManager.send_message_update data {data} conversation_id {conversation_id}")
        await rdb.publish(f"ws:message_update:{conversation_id}", json.dumps(data))

    async def edit_message(
        self,
        conversation_id,
        message_data: dict,
    ):
        await rdb.publish(
            f"ws:message_update:{conversation_id}",
            json.dumps(message_data),
        )

    async def delete_message(
        self,
        conversation_id,
        message_data: dict,
    ):
        await rdb.publish(
            f"ws:message_update:{conversation_id}",
            json.dumps(message_data),
        )


manager = ConnectionManager()