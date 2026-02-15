from fastapi import WebSocket
from typing import Dict
import logging

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(
            self,
            websocket: WebSocket,
            conversation_id: str,
            my_phone: str,
            peer_phone: str
    ):
        from app.consumers.telegram_listener import listener

        # Закрываем старое соединение если есть
        if conversation_id in self.active_connections:
            try:
                await self.active_connections[conversation_id].close()
            except Exception:
                pass
            del self.active_connections[conversation_id]

        await websocket.accept()
        self.active_connections[conversation_id] = websocket

        # peer_phone передаётся в listener
        await listener.start_listening(conversation_id, my_phone, peer_phone)

        log.info(f"Connected: conversation={conversation_id} my={my_phone} peer={peer_phone}")

    async def disconnect(self, conversation_id: str):
        from app.consumers.telegram_listener import listener

        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

        # Останавливаем listener через его собственный метод
        await listener.stop_listening(conversation_id)

        log.info(f"Disconnected: conversation={conversation_id}")

    async def send_new_message(self, conversation_id: str, message_data: dict):
        ws = self.active_connections.get(conversation_id)
        if not ws:
            return
        try:
            await ws.send_json({
                'type': 'new_message',
                'data': message_data
            })
        except Exception as e:
            log.error(f"send_new_message error for {conversation_id}: {e}")
            await self.disconnect(conversation_id)


manager = ConnectionManager()