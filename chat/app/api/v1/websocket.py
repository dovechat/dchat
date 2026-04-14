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
):
    user = await validate_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return 

    log.info(f"WebSocket connection attempt for conv {conversation_id}")
    await websocket.accept()
    log.info("WebSocket accepted")

    await manager.connect(
        websocket,
        conversation_id,
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


@router.websocket("/tenant/{tenant_id}")
async def tenant_websocket(
    websocket: WebSocket,
    tenant_id: str,
    token: str,
):
    user = await validate_token(token)
    if not user or user["tenant_id"] != tenant_id:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept()
    await manager.connect_tenant(websocket, tenant_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_tenant(tenant_id, websocket)
    except Exception as e:
        log.error(f"Tenant WS error: {e}")
        await manager.disconnect_tenant(tenant_id, websocket)