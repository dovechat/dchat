import asyncio
import json
import logging
from core.redis import rdb
from app.services.websocket_manager import manager

log = logging.getLogger(__name__)


async def redis_subscriber():
    pubsub = rdb.pubsub()
    await pubsub.psubscribe("ws:new_message:*", "ws:message_status:*", "ws:message_update:*")
    log.info("Redis subscriber started")
    async for message in pubsub.listen():
        if message["type"] not in ("pmessage", "message"):
            continue
        try:
            channel = message["channel"]
            data = json.loads(message["data"])
            conversation_id = str(channel).split(":", 2)[2]
            if "new_message" in channel:
                if conversation_id in manager.active_connections:
                    for ws in manager.active_connections[conversation_id][:]:
                        try:
                            await ws.send_json({"type": "new_message", "data": data})
                        except Exception as e:
                            log.error(f"redis_subscriber send_new_message error: {e}")
                            await manager.disconnect(conversation_id, ws)
            elif "message_status" in channel:
                if conversation_id in manager.active_connections:
                    for ws in manager.active_connections[conversation_id][:]:
                        try:
                            await ws.send_json({"type": "message_status", "data": data})
                        except Exception as e:
                            log.error(f"redis_subscriber send_message_status error: {e}")
            elif "message_update" in channel:
                if conversation_id in manager.active_connections:
                    for ws in manager.active_connections[conversation_id][:]:
                        try:
                            await ws.send_json({"type": "message_update", "data": data})
                        except Exception as e:
                            log.error(f"redis_subscriber send_message_update error: {e}")
        except Exception as e:
            log.error(f"redis_subscriber error: {e}")