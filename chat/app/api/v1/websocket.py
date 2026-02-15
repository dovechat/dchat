from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/chat/{conversation_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        conversation_id: str,
        my_phone: str,
        peer_phone: str
):
    my_phone = my_phone.strip()
    peer_phone = peer_phone.strip()
    if my_phone and my_phone[0] != '+':
        my_phone = '+' + my_phone
    if peer_phone and peer_phone[0] != '+':
        peer_phone = '+' + peer_phone

    if not my_phone or not peer_phone:
        await websocket.close(code=1008, reason="Phone numbers required")
        return

    log.info(f"WS connect: conversation={conversation_id} my={my_phone} peer={peer_phone}")

    # peer_phone теперь передаётся явно
    await manager.connect(websocket, conversation_id, my_phone, peer_phone)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(conversation_id)
    except Exception as e:
        log.error(f"WebSocket error: {e}")
        await manager.disconnect(conversation_id)


from app.services.websocket_manager import manager