from fastapi import WebSocket
from typing import Dict, List
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import get_db
from models.messages import Conversation
from models.tenants import ResourcePermission

import logging

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(
            self,
            websocket: WebSocket,
            conversation_id: str,
            my_phone: str,
            peer_phone: str,
            app,
            user_id: str,
            tenant_id: str,
            role: str,
    ) -> None:
        # Проверка доступа
        async for db in get_db():
            # Загружаем conversation вместе с линией
            stmt = select(Conversation).where(Conversation.id == conversation_id).options(
                selectinload(Conversation.line))
            result = await db.execute(stmt)
            conv = result.scalar_one_or_none()

            if not conv:
                await websocket.close(code=1008, reason="Conversation not found")
                return

            if role == "owner":
                if conv.line.tenant_id != uuid.UUID(tenant_id):
                    await websocket.close(code=1008, reason="Access denied")
                    return
            else:
                perm_query = select(ResourcePermission).where(
                    ResourcePermission.user_id == uuid.UUID(user_id),
                    ResourcePermission.resource_type == "line",
                    ResourcePermission.resource_id == conv.line_id,
                    ResourcePermission.action.in_(["owner", "member"])
                )
                result = await db.execute(perm_query)
                if not result.scalar_one_or_none():
                    await websocket.close(code=1008, reason="Access denied")
                    return
            break

        # Добавляем соединение в список
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        self.active_connections[conversation_id].append(websocket)

        # Если это первое соединение - запускаем listener
        if len(self.active_connections[conversation_id]) == 1:
            listener = app.state.listener
            log.info(f"+++++++++ listener.start_listening")
            await listener.start_listening(conversation_id, my_phone, peer_phone)
            log.info(f"+++++++++ listener.start_listening DONE")

        log.info(f"Connected: conversation={conversation_id}, total={len(self.active_connections[conversation_id])}")

    async def disconnect(self, conversation_id: str, websocket: WebSocket):
        listener = websocket.app.state.listener
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
                await listener.stop_listening(conversation_id)

        log.info(f"Disconnected: conversation={conversation_id}")

    async def send_new_message(self, conversation_id: str, message_data: dict):
        if conversation_id not in self.active_connections:
            return
        # Рассылаем всем соединениям
        for ws in self.active_connections[conversation_id][:]:  # копия списка
            try:
                await ws.send_json({
                    'type': 'new_message',
                    'data': message_data
                })
            except Exception as e:
                log.error(f"send_new_message error for {conversation_id}: {e}")
                await self.disconnect(conversation_id, ws)


manager = ConnectionManager()