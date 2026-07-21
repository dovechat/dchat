import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.websocket_service import WebSocketService
from models.messages import MessageDirection, MessageStatus


def make_service():
    db = AsyncMock()
    return WebSocketService(db), db


def make_result(conversation):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=conversation)
    return result


# ---------- subscribe_to_conversation ----------

@pytest.mark.asyncio
async def test_subscribe_success_adds_user():
    service, db = make_service()
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db.execute = AsyncMock(return_value=make_result(MagicMock()))

    await service.subscribe_to_conversation(conv_id, uuid.uuid4(), user_id)

    assert service.subscriptions[conv_id] == [user_id]


@pytest.mark.asyncio
async def test_subscribe_same_user_twice_not_duplicated():
    service, db = make_service()
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db.execute = AsyncMock(return_value=make_result(MagicMock()))

    await service.subscribe_to_conversation(conv_id, uuid.uuid4(), user_id)
    await service.subscribe_to_conversation(conv_id, uuid.uuid4(), user_id)

    assert service.subscriptions[conv_id] == [user_id]


@pytest.mark.asyncio
async def test_subscribe_not_found_raises_valueerror():
    service, db = make_service()
    db.execute = AsyncMock(return_value=make_result(None))

    with pytest.raises(ValueError):
        await service.subscribe_to_conversation(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


# ---------- save_message ----------

@pytest.mark.asyncio
async def test_save_message_not_found_raises_valueerror():
    service, db = make_service()
    db.execute = AsyncMock(return_value=make_result(None))

    with pytest.raises(ValueError):
        await service.save_message(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), {"text": "hi"})

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_message_success_persists_and_returns_dict():
    service, db = make_service()
    conv_id = uuid.uuid4()
    conversation = MagicMock()

    db.execute = AsyncMock(return_value=make_result(conversation))

    fixed_created_at = datetime.now(timezone.utc)

    async def fake_refresh(obj):
        obj.id = 42
        obj.created_at = fixed_created_at

    db.refresh = AsyncMock(side_effect=fake_refresh)

    message = {"text": "hello", "media_id": None}
    result = await service.save_message(conv_id, uuid.uuid4(), uuid.uuid4(), message)

    db.add.assert_called_once()
    added_obj = db.add.call_args.args[0]
    assert added_obj.conversation_id == conv_id
    assert added_obj.direction == MessageDirection.outbound
    assert added_obj.status == MessageStatus.sent
    assert added_obj.text == "hello"
    assert added_obj.raw_content == message

    assert db.commit.await_count == 2
    assert db.execute.await_count == 2  # select conversation + update conversation

    assert result["id"] == 42
    assert result["conversation_id"] == str(conv_id)
    assert result["direction"] == MessageDirection.outbound.value
    assert result["status"] == MessageStatus.sent.value
    assert result["text"] == "hello"
    assert result["created_at"] == fixed_created_at.isoformat()
    assert result["raw_content"] == message


# ---------- get_subscribed_users ----------

@pytest.mark.asyncio
async def test_get_subscribed_users_returns_list():
    service, _ = make_service()
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    service.subscriptions[conv_id] = [user_id]

    result = await service.get_subscribed_users(conv_id)

    assert result == [user_id]


@pytest.mark.asyncio
async def test_get_subscribed_users_unknown_conversation_returns_empty():
    service, _ = make_service()
    result = await service.get_subscribed_users(uuid.uuid4())
    assert result == []


# ---------- unsubscribe_from_conversation ----------

@pytest.mark.asyncio
async def test_unsubscribe_removes_user_and_key_when_empty():
    service, _ = make_service()
    conv_id = uuid.uuid4()
    user_id = uuid.uuid4()
    service.subscriptions[conv_id] = [user_id]

    await service.unsubscribe_from_conversation(conv_id, user_id)

    assert conv_id not in service.subscriptions


@pytest.mark.asyncio
async def test_unsubscribe_keeps_key_when_others_remain():
    service, _ = make_service()
    conv_id = uuid.uuid4()
    user1, user2 = uuid.uuid4(), uuid.uuid4()
    service.subscriptions[conv_id] = [user1, user2]

    await service.unsubscribe_from_conversation(conv_id, user1)

    assert service.subscriptions[conv_id] == [user2]


@pytest.mark.asyncio
async def test_unsubscribe_unknown_user_no_crash():
    service, _ = make_service()
    conv_id = uuid.uuid4()
    service.subscriptions[conv_id] = [uuid.uuid4()]

    await service.unsubscribe_from_conversation(conv_id, uuid.uuid4())

    assert len(service.subscriptions[conv_id]) == 1


@pytest.mark.asyncio
async def test_unsubscribe_unknown_conversation_no_crash():
    service, _ = make_service()
    await service.unsubscribe_from_conversation(uuid.uuid4(), uuid.uuid4())