import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.webhook_service import (
    IncomingMessageHandler,
    MessageStatusHandler,
    StateChangedHandler,
    WebhookHandlerFactory,
    WebhookService,
)


def make_service():
    db = MagicMock()
    service = WebhookService(db)
    service.channel_repo = AsyncMock()
    service.line_repo = AsyncMock()
    service.chat_repo = AsyncMock()
    service.instance_repo = AsyncMock()
    service.services["chat_service"] = AsyncMock()
    service.services["channel_repo"] = service.channel_repo
    return service


# ---------- WebhookHandlerFactory ----------

@pytest.mark.parametrize(
    "event_type,expected_cls",
    [
        ("incomingMessageReceived", IncomingMessageHandler),
        ("outgoingMessageStatus", MessageStatusHandler),
        ("stateInstanceChanged", StateChangedHandler),
        ("statusInstanceChanged", StateChangedHandler),
    ],
)
def test_get_handler_known_types(event_type, expected_cls):
    handler = WebhookHandlerFactory.get_handler(event_type)
    assert isinstance(handler, expected_cls)


def test_get_handler_unknown_type_returns_none():
    assert WebhookHandlerFactory.get_handler("somethingElse") is None


# ---------- IncomingMessageHandler ----------

@pytest.mark.asyncio
async def test_incoming_message_handler_no_text_skips():
    chat_service = AsyncMock()
    handler = IncomingMessageHandler()
    payload = {"messageData": {}, "senderData": {"chatId": "1@c.us"}}
    await handler.handle("conv-1", payload, {"chat_service": chat_service})
    chat_service.save_incoming_green.assert_not_called()


@pytest.mark.asyncio
async def test_incoming_message_handler_saves_message():
    chat_service = AsyncMock()
    chat_service.save_incoming_green = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    handler = IncomingMessageHandler()
    payload = {
        "messageData": {"textMessageData": {"textMessage": "hi"}},
        "senderData": {"chatId": "1@c.us"},
    }
    await handler.handle("conv-1", payload, {"chat_service": chat_service})
    chat_service.save_incoming_green.assert_awaited_once_with(conversation_id="conv-1", payload=payload)


# ---------- MessageStatusHandler ----------

@pytest.mark.asyncio
async def test_status_handler_missing_fields_skips():
    chat_service = AsyncMock()
    handler = MessageStatusHandler()
    await handler.handle("line-1", {"idMessage": None, "status": None}, {"chat_service": chat_service})
    chat_service.update_message_status.assert_not_called()


@pytest.mark.asyncio
async def test_status_handler_updates_status():
    chat_service = AsyncMock()
    handler = MessageStatusHandler()
    payload = {"idMessage": "ext-1", "status": "delivered"}
    await handler.handle("line-1", payload, {"chat_service": chat_service})
    chat_service.update_message_status.assert_awaited_once_with(external_id="ext-1", status="delivered")


# ---------- StateChangedHandler ----------

@pytest.mark.asyncio
async def test_state_handler_not_authorized_skips():
    channel_repo = AsyncMock()
    handler = StateChangedHandler()
    payload = {"instanceData": {"wid": "79990001122@c.us"}, "stateInstance": "notAuthorized"}
    await handler.handle("line-1", payload, {"channel_repo": channel_repo})
    channel_repo.get_by_line_id.assert_not_called()


@pytest.mark.asyncio
async def test_state_handler_no_phone_skips():
    channel_repo = AsyncMock()
    handler = StateChangedHandler()
    payload = {"instanceData": {}, "stateInstance": "authorized"}
    await handler.handle("line-1", payload, {"channel_repo": channel_repo})
    channel_repo.get_by_line_id.assert_not_called()


@pytest.mark.asyncio
async def test_state_handler_account_not_found_skips_update():
    channel_repo = AsyncMock()
    channel_repo.get_by_line_id = AsyncMock(return_value=None)
    handler = StateChangedHandler()
    payload = {"instanceData": {"wid": "79990001122@c.us"}, "stateInstance": "authorized"}
    await handler.handle("line-1", payload, {"channel_repo": channel_repo})
    channel_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_state_handler_authorized_updates_account():
    from datetime import datetime

    channel_repo = AsyncMock()
    account = SimpleNamespace(id=uuid.uuid4())
    channel_repo.get_by_line_id = AsyncMock(return_value=account)
    handler = StateChangedHandler()
    payload = {"instanceData": {"wid": "79990001122@c.us"}, "stateInstance": "authorized"}
    await handler.handle("line-1", payload, {"channel_repo": channel_repo})
    channel_repo.update.assert_awaited_once()
    call_kwargs = channel_repo.update.call_args.kwargs
    assert call_kwargs["connection_status"] == "connected"
    assert call_kwargs["phone"] == "79990001122"
    assert isinstance(call_kwargs["last_checked_at"], datetime)


# ---------- WebhookService.process_green_webhook ----------

@pytest.mark.asyncio
async def test_process_green_webhook_no_instance_id_returns():
    service = make_service()
    await service.process_green_webhook({"typeWebhook": "incomingMessageReceived"})
    service.instance_repo.get_line_by_instance_id.assert_not_called()


@pytest.mark.asyncio
async def test_process_green_webhook_line_not_found_returns():
    service = make_service()
    service.instance_repo.get_line_by_instance_id = AsyncMock(return_value=None)
    payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": "123"},
        "senderData": {"chatId": "1@c.us"},
    }
    await service.process_green_webhook(payload)
    service.chat_repo.get_conversations_by_phone.assert_not_called()


@pytest.mark.asyncio
async def test_process_green_webhook_conv_none_raises_attributeerror():
    # bug: conv is used as conv.id without a None check
    service = make_service()
    line = SimpleNamespace(id=uuid.uuid4())
    service.instance_repo.get_line_by_instance_id = AsyncMock(return_value=line)
    service.chat_repo.get_conversations_by_phone = AsyncMock(return_value=None)
    payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": "123"},
        "senderData": {"chatId": "1@c.us"},
    }
    with pytest.raises(AttributeError):
        await service.process_green_webhook(payload)


@pytest.mark.asyncio
async def test_process_green_webhook_dispatches_to_handler():
    service = make_service()
    line = SimpleNamespace(id=uuid.uuid4())
    conv = SimpleNamespace(id=uuid.uuid4())
    service.instance_repo.get_line_by_instance_id = AsyncMock(return_value=line)
    service.chat_repo.get_conversations_by_phone = AsyncMock(return_value=conv)
    payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {"idInstance": "123"},
        "senderData": {"chatId": "1@c.us"},
    }
    with patch.object(
        WebhookHandlerFactory, "get_handler", return_value=AsyncMock()
    ) as mock_get_handler:
        handler_instance = mock_get_handler.return_value
        await service.process_green_webhook(payload)

    handler_instance.handle.assert_awaited_once_with(conv.id, payload, service.services)


@pytest.mark.asyncio
async def test_process_green_webhook_unhandled_type_no_crash():
    service = make_service()
    line = SimpleNamespace(id=uuid.uuid4())
    conv = SimpleNamespace(id=uuid.uuid4())
    service.instance_repo.get_line_by_instance_id = AsyncMock(return_value=line)
    service.chat_repo.get_conversations_by_phone = AsyncMock(return_value=conv)
    payload = {
        "typeWebhook": "somethingUnknown",
        "instanceData": {"idInstance": "123"},
        "senderData": {"chatId": "1@c.us"},
    }
    await service.process_green_webhook(payload)