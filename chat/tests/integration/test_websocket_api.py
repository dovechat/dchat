import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from unittest.mock import AsyncMock, patch

from app.api.v1.websocket import router as websocket_router, validate_token


def make_app():
    app = FastAPI()
    app.include_router(websocket_router)
    return app


# ---------- validate_token ----------

@pytest.mark.asyncio
async def test_validate_token_valid():
    with patch("app.api.v1.websocket.jwt.decode", return_value={"sub": "u1"}):
        result = await validate_token("good-token")
    assert result == {"sub": "u1"}


@pytest.mark.asyncio
async def test_validate_token_invalid():
    import jwt

    with patch("app.api.v1.websocket.jwt.decode", side_effect=jwt.PyJWTError()):
        result = await validate_token("bad-token")
    assert result is None


# ---------- /chat/{conversation_id} ----------

def test_chat_ws_unauthorized_closes():
    app = make_app()
    client = TestClient(app)
    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=None)):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/chat/conv-1?token=bad"):
                pass


def test_chat_ws_success_connects_and_disconnects():
    app = make_app()
    client = TestClient(app)
    user = {"sub": "user-1", "tenant_id": "tenant-1", "role": "agent"}

    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=user)), \
         patch("app.api.v1.websocket.manager") as mock_manager:
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        with client.websocket_connect("/chat/conv-1?token=good"):
            pass

    mock_manager.connect.assert_awaited_once()
    call = mock_manager.connect.call_args
    assert call.args[1] == "conv-1"
    assert call.kwargs["user_id"] == "user-1"
    assert call.kwargs["tenant_id"] == "tenant-1"
    assert call.kwargs["role"] == "agent"
    mock_manager.disconnect.assert_awaited_once_with("conv-1", mock_manager.disconnect.call_args.args[1])


# ---------- /tenant/{tenant_id} ----------

def test_tenant_ws_mismatched_tenant_closes():
    app = make_app()
    client = TestClient(app)
    user = {"sub": "user-1", "tenant_id": "tenant-A", "role": "agent"}

    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=user)):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/tenant/tenant-B?token=good"):
                pass


def test_tenant_ws_unauthorized_closes():
    app = make_app()
    client = TestClient(app)
    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=None)):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/tenant/tenant-A?token=bad"):
                pass


def test_tenant_ws_success_connects_and_disconnects():
    app = make_app()
    client = TestClient(app)
    user = {"sub": "user-1", "tenant_id": "tenant-A", "role": "agent"}

    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=user)), \
         patch("app.api.v1.websocket.manager") as mock_manager:
        mock_manager.connect_tenant = AsyncMock()
        mock_manager.disconnect_tenant = AsyncMock()

        with client.websocket_connect("/tenant/tenant-A?token=good"):
            pass

    mock_manager.connect_tenant.assert_awaited_once()
    assert mock_manager.connect_tenant.call_args.args[1] == "tenant-A"
    mock_manager.disconnect_tenant.assert_awaited_once()


# ---------- /user ----------

def test_user_ws_unauthorized_closes():
    app = make_app()
    client = TestClient(app)
    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=None)):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/user?token=bad"):
                pass


def test_user_ws_success_uses_user_id_as_connect_key():
    app = make_app()
    client = TestClient(app)
    user = {"sub": "user-42", "tenant_id": "tenant-A", "role": "agent"}

    with patch("app.api.v1.websocket.validate_token", new=AsyncMock(return_value=user)), \
         patch("app.api.v1.websocket.manager") as mock_manager:
        mock_manager.connect_tenant = AsyncMock()
        mock_manager.disconnect_tenant = AsyncMock()

        with client.websocket_connect("/user?token=good"):
            pass

    mock_manager.connect_tenant.assert_awaited_once()
    assert mock_manager.connect_tenant.call_args.args[1] == "user-42"
    mock_manager.disconnect_tenant.assert_awaited_once()