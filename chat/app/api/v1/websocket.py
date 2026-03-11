from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import jwt
from core.config import settings
from app.services.websocket_manager import manager

log = logging.getLogger(__name__)

router = APIRouter()

async def validate_token(token: str):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except jwt.PyJWTError:
        return None

@router.websocket("/chat/{conversation_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        conversation_id: str,
        token: str,
        my_phone: str | None = None,
        peer_phone: str | None = None
):
    user = await validate_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return 

    log.info(f"WebSocket connection attempt for conv {conversation_id}")
    await websocket.accept()
    log.info("WebSocket accepted")

    if my_phone:
        my_phone = my_phone.strip()
        if my_phone and my_phone[0] != '+':
            my_phone = '+' + my_phone

    if peer_phone:
        peer_phone = peer_phone.strip()
        if peer_phone and peer_phone[0] != '+':
            peer_phone = '+' + peer_phone

    if not peer_phone:
        await websocket.close(code=1008, reason="Peer phone required")
        return

    log.info(f"WS connect: conversation={conversation_id} my={my_phone} peer={peer_phone}")

    await manager.connect(
        websocket,
        conversation_id,
        my_phone,
        peer_phone,
        app=websocket.app,
        user_id=user["sub"],
        tenant_id=user["tenant_id"],
        role=user["role"]
    )

    log.info("+++*** Manager connect done")

    try:
        while True:
            log.info("Waiting for message...")
            await websocket.receive_text()
            log.info(f"Received: {message}")
    except WebSocketDisconnect:
        log.info("Client disconnected normally")
        await manager.disconnect(conversation_id, websocket)
    except Exception as e:
        log.error(f"ERROR: WebSocket error: {e}")
        await manager.disconnect(conversation_id, websocket)