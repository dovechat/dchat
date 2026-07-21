import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bot_service import BotService


def make_service():
    db = MagicMock()
    db.get = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    service = BotService(db)
    service.channel_repo = AsyncMock()
    service.conv_repo = AsyncMock()
    service.msg_repo = AsyncMock()
    service.media_repo = AsyncMock()
    service.membership_repo = AsyncMock()
    service.storage = AsyncMock()
    service.storage.presigned_url = MagicMock(return_value="http://s3/file")
    return service


def make_line():
    return SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())


def make_conversation():
    return SimpleNamespace(id=uuid.uuid4(), crm_chat_id=None)


def make_db_message():
    return SimpleNamespace(id=uuid.uuid4(), created_at=datetime.now(timezone.utc))


# ---------- handle_webhook ----------

@pytest.mark.asyncio
async def test_handle_webhook_line_not_found():
    service = make_service()
    service.db.get = AsyncMock(return_value=None)
    result = await service.handle_webhook(uuid.uuid4(), {}, MagicMock(headers={}))
    assert result == {"ok": False}


@pytest.mark.asyncio
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_invalid_secret_token(mock_decrypt):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "expected"}
    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "wrong"})
    result = await service.handle_webhook(line.id, {"message": {}}, request)
    assert result == {"ok": True}
    service.conv_repo.get_or_create_by_chat_id.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_edited_message_delegates(mock_decrypt):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s"}
    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
    edited = {"chat": {"id": 1}, "message_id": 2, "text": "hi"}
    with patch.object(service, "_handle_edited_message", new=AsyncMock(return_value={"ok": True})) as mock_edit:
        result = await service.handle_webhook(line.id, {"edited_message": edited}, request)
    mock_edit.assert_called_once_with(line.id, line, edited)
    assert result == {"ok": True}


@pytest.mark.asyncio
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_ignores_non_message(mock_decrypt):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s"}
    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
    result = await service.handle_webhook(line.id, {"message": {"chat": {}}}, request)
    assert result == {"ok": True}
    service.conv_repo.get_or_create_by_chat_id.assert_not_called()


@pytest.mark.asyncio
@patch("crm.app.core.uow.CrmUnitOfWork")
@patch("crm.app.services.crm_service.CrmService")
@patch("app.services.websocket_manager.manager")
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_success_existing_conversation(mock_decrypt, mock_manager, mock_crm_cls, mock_uow_cls):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s", "bot_token": "t"}
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, False))
    db_message = make_db_message()
    service.msg_repo.create_message = AsyncMock(return_value=db_message)
    mock_manager.send_new_message = AsyncMock()
    mock_crm_cls.return_value.send_to_crm = AsyncMock(return_value=None)

    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
    update_data = {"message": {"chat": {"id": 123, "username": "bob"}, "message_id": 5, "text": "hi"}}

    result = await service.handle_webhook(line.id, update_data, request)

    assert result == {"ok": True}
    service.msg_repo.create_message.assert_awaited_once()
    mock_manager.send_new_message.assert_awaited_once()
    mock_manager.send_new_conversation.assert_not_called()


@pytest.mark.asyncio
@patch("crm.app.core.uow.CrmUnitOfWork")
@patch("crm.app.services.crm_service.CrmService")
@patch("app.services.websocket_manager.manager")
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_new_conversation_notifies_members(mock_decrypt, mock_manager, mock_crm_cls, mock_uow_cls):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s", "bot_token": "t"}
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, True))
    db_message = make_db_message()
    service.msg_repo.create_message = AsyncMock(return_value=db_message)
    member = SimpleNamespace(user_id=uuid.uuid4())
    service.membership_repo.get_by_tenant = AsyncMock(return_value=[member])
    mock_manager.send_new_conversation = AsyncMock()
    mock_manager.send_new_message = AsyncMock()
    mock_crm_cls.return_value.send_to_crm = AsyncMock(return_value=None)

    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
    update_data = {"message": {"chat": {"id": 123}, "message_id": 5, "text": "hi"}}

    await service.handle_webhook(line.id, update_data, request)

    mock_manager.send_new_conversation.assert_awaited_once()


@pytest.mark.asyncio
@patch("crm.app.core.uow.CrmUnitOfWork")
@patch("crm.app.services.crm_service.CrmService")
@patch("app.services.websocket_manager.manager")
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_with_media(mock_decrypt, mock_manager, mock_crm_cls, mock_uow_cls):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s", "bot_token": "t"}
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, False))
    db_message = make_db_message()
    service.msg_repo.create_message = AsyncMock(return_value=db_message)
    mock_manager.send_new_message = AsyncMock()
    mock_crm_cls.return_value.send_to_crm = AsyncMock(return_value=None)

    media_id = str(uuid.uuid4())
    with patch.object(
        service, "_process_media_message",
        new=AsyncMock(return_value=(media_id, "photo.jpg", "image/jpeg", {}, 1234)),
    ):
        request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
        update_data = {"message": {"chat": {"id": 123}, "message_id": 5, "photo": [{}]}}
        result = await service.handle_webhook(line.id, update_data, request)

    assert result == {"ok": True}
    service.media_repo.create.assert_awaited_once()
    service.db.flush.assert_awaited_once()


@pytest.mark.asyncio
@patch("crm.app.core.uow.CrmUnitOfWork")
@patch("crm.app.services.crm_service.CrmService")
@patch("app.services.websocket_manager.manager")
@patch("app.services.bot_service.decrypt_credentials")
async def test_handle_webhook_crm_failure_swallowed(mock_decrypt, mock_manager, mock_crm_cls, mock_uow_cls):
    service = make_service()
    line = make_line()
    service.db.get = AsyncMock(return_value=line)
    service.channel_repo.get_by_line_and_type = AsyncMock(return_value=MagicMock(credentials_encrypted="x"))
    mock_decrypt.return_value = {"secret_token": "s", "bot_token": "t"}
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, False))
    db_message = make_db_message()
    service.msg_repo.create_message = AsyncMock(return_value=db_message)
    mock_manager.send_new_message = AsyncMock()
    mock_crm_cls.return_value.send_to_crm = AsyncMock(side_effect=Exception("boom"))

    request = MagicMock(headers={"x-telegram-bot-api-secret-token": "s"})
    update_data = {"message": {"chat": {"id": 123}, "message_id": 5, "text": "hi"}}

    result = await service.handle_webhook(line.id, update_data, request)

    assert result == {"ok": True}


# ---------- _handle_edited_message ----------

@pytest.mark.asyncio
async def test_handle_edited_message_missing_ids():
    service = make_service()
    line = make_line()
    result = await service._handle_edited_message(line.id, line, {"chat": {}, "text": "x"})
    assert result == {"ok": True}
    service.conv_repo.get_or_create_by_chat_id.assert_not_called()


@pytest.mark.asyncio
async def test_handle_edited_message_not_found():
    service = make_service()
    line = make_line()
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, False))
    service.msg_repo.get_multi = AsyncMock(return_value=[])
    result = await service._handle_edited_message(
        line.id, line, {"chat": {"id": 1}, "message_id": 2, "text": "new"}
    )
    assert result == {"ok": True}
    service.msg_repo.update.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.websocket_manager.manager")
async def test_handle_edited_message_success(mock_manager):
    service = make_service()
    line = make_line()
    conversation = make_conversation()
    service.conv_repo.get_or_create_by_chat_id = AsyncMock(return_value=(conversation, False))
    db_message = make_db_message()
    service.msg_repo.get_multi = AsyncMock(return_value=[db_message])
    mock_manager.send_message_update = AsyncMock()

    result = await service._handle_edited_message(
        line.id, line, {"chat": {"id": 1}, "message_id": 2, "text": "edited text"}
    )

    assert result == {"ok": True}
    service.msg_repo.update.assert_awaited_once_with(db_message, text="edited text")
    service.db.commit.assert_awaited_once()
    mock_manager.send_message_update.assert_awaited_once()


# ---------- _process_media_message ----------

@pytest.mark.asyncio
async def test_process_media_message_photo_success():
    service = make_service()
    message = {"photo": [{"file_id": "small"}, {"file_id": "big"}]}
    file_info_resp = MagicMock()
    file_info_resp.json.return_value = {"ok": True, "result": {"file_path": "path/x.jpg"}}
    file_resp = MagicMock()
    file_resp.content = b"binarydata"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=file_info_resp)
    mock_client.get = AsyncMock(return_value=file_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.bot_service.httpx.AsyncClient", return_value=mock_client):
        media_id, file_name, mime_type, raw_content, file_size = await service._process_media_message(
            message, "token", {}
        )

    assert media_id is not None
    assert file_name == "photo_big.jpg"
    assert mime_type == "image/jpeg"
    assert file_size == len(b"binarydata")
    assert raw_content["file_name"] == file_name
    service.storage.save_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_media_message_document_success():
    service = make_service()
    message = {"document": {"file_id": "doc1", "file_name": "report.pdf", "mime_type": "application/pdf"}}
    file_info_resp = MagicMock()
    file_info_resp.json.return_value = {"ok": True, "result": {"file_path": "path/report.pdf"}}
    file_resp = MagicMock()
    file_resp.content = b"pdfbytes"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=file_info_resp)
    mock_client.get = AsyncMock(return_value=file_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.bot_service.httpx.AsyncClient", return_value=mock_client):
        media_id, file_name, mime_type, raw_content, file_size = await service._process_media_message(
            message, "token", {}
        )

    assert file_name == "report.pdf"
    assert mime_type == "application/pdf"
    assert file_size == len(b"pdfbytes")


@pytest.mark.asyncio
async def test_process_media_message_get_file_fails():
    service = make_service()
    message = {"photo": [{"file_id": "x"}]}
    file_info_resp = MagicMock()
    file_info_resp.json.return_value = {"ok": False}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=file_info_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.bot_service.httpx.AsyncClient", return_value=mock_client):
        result = await service._process_media_message(message, "token", {})

    assert result == (None, None, None, None)


@pytest.mark.asyncio
async def test_process_media_message_exception_returns_none():
    service = make_service()
    message = {"photo": [{"file_id": "x"}]}
    with patch("app.services.bot_service.httpx.AsyncClient", side_effect=Exception("boom")):
        result = await service._process_media_message(message, "token", {})
    assert result == (None, None, None, None)


@pytest.mark.asyncio
async def test_process_media_message_no_recognized_media_key():
    service = make_service()
    message = {"video": {"file_id": "v1"}}
    result = await service._process_media_message(message, "token", {})
    assert result == (None, None, None, None)


# ---------- send_message ----------

@pytest.mark.asyncio
async def test_send_message_success():
    service = make_service()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"ok": True}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.bot_service.httpx.AsyncClient", return_value=mock_client):
        result = await service.send_message("token", "123", "hello")

    assert result == {"ok": True}
    mock_client.post.assert_awaited_once()