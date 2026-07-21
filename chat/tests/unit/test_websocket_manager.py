import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.websocket_manager import ConnectionManager


def fake_get_session_factory(db):
    @asynccontextmanager
    async def _cm():
        yield db
    return _cm


def make_db(conv=None, my_phone="79990001111", membership=None):
    conv_result = MagicMock()
    conv_result.scalar_one_or_none = MagicMock(return_value=conv)
    phone_result = MagicMock()
    phone_result.scalar_one_or_none = MagicMock(return_value=my_phone)
    db = AsyncMock()
    if conv is None:
        db.execute = AsyncMock(side_effect=[conv_result])
    else:
        db.execute = AsyncMock(side_effect=[conv_result, phone_result])
    return db


def make_conv(channel_type="telegram_user", tenant_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        channel_type=channel_type,
        client_phone="79990002222",
        line=SimpleNamespace(tenant_id=tenant_id or uuid.uuid4()),
    )


# ---------- connect ----------

@pytest.mark.asyncio
async def test_connect_conversation_not_found_closes_socket():
    manager = ConnectionManager()
    db = make_db(conv=None)
    websocket = MagicMock()
    websocket.close = AsyncMock()

    with patch("app.services.websocket_manager.get_session", fake_get_session_factory(db)):
        await manager.connect(websocket, "conv-1", MagicMock(), str(uuid.uuid4()), "tenant-1", "agent")

    websocket.close.assert_awaited_once_with(code=1008, reason="Conversation not found")
    assert "conv-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_connect_no_membership_raises_attributeerror():
    # bug: membership.is_active is accessed for logging before the None-check closes the socket
    manager = ConnectionManager()
    conv = make_conv()
    db = make_db(conv=conv)
    websocket = MagicMock()
    websocket.close = AsyncMock()

    mock_user_repo = AsyncMock()
    mock_user_repo.get_membership = AsyncMock(return_value=None)

    with patch("app.services.websocket_manager.get_session", fake_get_session_factory(db)), \
         patch("app.services.websocket_manager.UserRepository", return_value=mock_user_repo):
        with pytest.raises(AttributeError):
            await manager.connect(websocket, "conv-1", MagicMock(), str(uuid.uuid4()), "tenant-1", "agent")


@pytest.mark.asyncio
async def test_connect_success_first_connection_starts_listener_for_telegram_user():
    manager = ConnectionManager()
    conv = make_conv(channel_type="telegram_user")
    db = make_db(conv=conv)
    websocket = MagicMock()
    websocket.client_state = SimpleNamespace(name="CONNECTED")

    membership = SimpleNamespace(is_active=True)
    mock_user_repo = AsyncMock()
    mock_user_repo.get_membership = AsyncMock(return_value=membership)

    app = MagicMock()
    app.state.listener = AsyncMock()

    with patch("app.services.websocket_manager.get_session", fake_get_session_factory(db)), \
         patch("app.services.websocket_manager.UserRepository", return_value=mock_user_repo):
        await manager.connect(websocket, "conv-1", app, str(uuid.uuid4()), "tenant-1", "agent")

    assert manager.active_connections["conv-1"] == [websocket]
    app.state.listener.start_listening.assert_awaited_once_with("conv-1", "79990001111", "79990002222")


@pytest.mark.asyncio
async def test_connect_success_non_telegram_user_skips_listener():
    manager = ConnectionManager()
    conv = make_conv(channel_type="whatsapp_green")
    db = make_db(conv=conv)
    websocket = MagicMock()
    websocket.client_state = SimpleNamespace(name="CONNECTED")

    membership = SimpleNamespace(is_active=True)
    mock_user_repo = AsyncMock()
    mock_user_repo.get_membership = AsyncMock(return_value=membership)

    app = MagicMock()
    app.state.listener = AsyncMock()

    with patch("app.services.websocket_manager.get_session", fake_get_session_factory(db)), \
         patch("app.services.websocket_manager.UserRepository", return_value=mock_user_repo):
        await manager.connect(websocket, "conv-1", app, str(uuid.uuid4()), "tenant-1", "agent")

    app.state.listener.start_listening.assert_not_called()


@pytest.mark.asyncio
async def test_connect_second_connection_skips_listener():
    manager = ConnectionManager()
    existing_ws = MagicMock()
    manager.active_connections["conv-1"] = [existing_ws]

    conv = make_conv(channel_type="telegram_user")
    db = make_db(conv=conv)
    websocket = MagicMock()
    websocket.client_state = SimpleNamespace(name="CONNECTED")

    membership = SimpleNamespace(is_active=True)
    mock_user_repo = AsyncMock()
    mock_user_repo.get_membership = AsyncMock(return_value=membership)

    app = MagicMock()
    app.state.listener = AsyncMock()

    with patch("app.services.websocket_manager.get_session", fake_get_session_factory(db)), \
         patch("app.services.websocket_manager.UserRepository", return_value=mock_user_repo):
        await manager.connect(websocket, "conv-1", app, str(uuid.uuid4()), "tenant-1", "agent")

    assert manager.active_connections["conv-1"] == [existing_ws, websocket]
    app.state.listener.start_listening.assert_not_called()


# ---------- disconnect ----------

@pytest.mark.asyncio
async def test_disconnect_removes_socket_and_key_when_empty():
    manager = ConnectionManager()
    websocket = MagicMock()
    manager.active_connections["conv-1"] = [websocket]

    await manager.disconnect("conv-1", websocket)

    assert "conv-1" not in manager.active_connections


@pytest.mark.asyncio
async def test_disconnect_keeps_key_when_others_remain():
    manager = ConnectionManager()
    ws1, ws2 = MagicMock(), MagicMock()
    manager.active_connections["conv-1"] = [ws1, ws2]

    await manager.disconnect("conv-1", ws1)

    assert manager.active_connections["conv-1"] == [ws2]


@pytest.mark.asyncio
async def test_disconnect_unknown_conversation_no_crash():
    manager = ConnectionManager()
    await manager.disconnect("missing-conv", MagicMock())


# ---------- pubsub senders ----------

@pytest.mark.asyncio
async def test_send_new_message_publishes_to_redis():
    manager = ConnectionManager()
    with patch("app.services.websocket_manager.rdb") as mock_rdb:
        mock_rdb.publish = AsyncMock()
        await manager.send_new_message("conv-1", {"text": "hi"})
    mock_rdb.publish.assert_awaited_once_with("ws:new_message:conv-1", json.dumps({"text": "hi"}))


@pytest.mark.asyncio
async def test_send_message_status_publishes_to_redis():
    manager = ConnectionManager()
    with patch("app.services.websocket_manager.rdb") as mock_rdb:
        mock_rdb.publish = AsyncMock()
        await manager.send_message_status("conv-1", {"status": "sent"})
    mock_rdb.publish.assert_awaited_once_with("ws:message_status:conv-1", json.dumps({"status": "sent"}))


@pytest.mark.asyncio
async def test_send_message_update_publishes_to_redis():
    manager = ConnectionManager()
    with patch("app.services.websocket_manager.rdb") as mock_rdb:
        mock_rdb.publish = AsyncMock()
        await manager.send_message_update("conv-1", {"text": "edited"})
    mock_rdb.publish.assert_awaited_once_with("ws:message_update:conv-1", json.dumps({"text": "edited"}))


# ---------- tenant connections ----------

@pytest.mark.asyncio
async def test_connect_tenant_and_disconnect_tenant():
    manager = ConnectionManager()
    websocket = MagicMock()

    await manager.connect_tenant(websocket, "tenant-1")
    assert manager.tenant_connections["tenant-1"] == [websocket]

    await manager.disconnect_tenant("tenant-1", websocket)
    assert "tenant-1" not in manager.tenant_connections


@pytest.mark.asyncio
async def test_send_new_conversation_sends_to_all_and_swallows_errors():
    manager = ConnectionManager()
    ok_ws = MagicMock()
    ok_ws.send_json = AsyncMock()
    failing_ws = MagicMock()
    failing_ws.send_json = AsyncMock(side_effect=Exception("boom"))
    manager.tenant_connections["tenant-1"] = [ok_ws, failing_ws]

    await manager.send_new_conversation("tenant-1", {"id": "conv-1"})

    ok_ws.send_json.assert_awaited_once_with({"type": "new_conversation", "data": {"id": "conv-1"}})
    failing_ws.send_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_new_conversation_unknown_tenant_no_crash():
    manager = ConnectionManager()
    await manager.send_new_conversation("missing-tenant", {"id": "conv-1"})