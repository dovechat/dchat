import base64
import httpx
import json
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import MessageCreate, MessageStatus
from models.messages import Conversation, Message, MessageDirection
from models.lines import Line
from unittest.mock import call
from fastapi import HTTPException, UploadFile
from datetime import datetime as dt, timezone as tz




@pytest.fixture
def test_message():
    m = MagicMock()
    m.id = 1
    m.conversation_id = uuid.uuid4()
    m.channel_msg_id = "ext-1"
    m.direction = MessageDirection.outbound
    m.status = MessageStatus.sent
    m.text = "hi"
    m.raw_content = {}
    m.created_at = datetime.now(timezone.utc)
    m.user_id = None
    m.user_email = None
    m.user_full_name = None
    m.media = []
    return m


@pytest.fixture
def channel_acc():
    acc = MagicMock()
    acc.line_id = uuid.uuid4()
    acc.credentials_encrypted = {"encrypted_data": "enc"}
    acc.channel_type = "telegram_bot"
    return acc


@pytest.fixture
def chat_service(mock_db):
    return ChatService(mock_db)


@pytest.fixture
def test_tenant_id():
    return uuid.uuid4()

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Мокаем execute чтобы возвращал объект с scalars()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


@pytest.fixture
def test_conversation():
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.line_id = uuid.uuid4()
    conv.channel_type = "bitrix24"
    conv.crm_chat_id = "chat123"
    conv.client_phone = "+79123456789"
    conv.meta = {}
    conv.created_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)
    return conv


@pytest.fixture
def message_create_data():
    return MessageCreate(
        conversation_id=uuid.uuid4(),
        direction=MessageDirection.outbound,
        text="hello",
        channel_msg_id=None,
        raw_content={},
        media=[],
    )


@pytest.fixture
def current_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


class TestChatService:
    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, chat_service, mock_db, test_tenant_id):
        mock_db.execute.return_value.all.return_value = []

        result = await chat_service.get_conversations(test_tenant_id)

        assert result == []
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, chat_service, mock_db, test_tenant_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await chat_service.get_conversation(uuid.uuid4(), test_tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_messages_no_access(self, chat_service, mock_db):
        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=None)

        result = await chat_service.get_messages(
            conversation_id=uuid.uuid4(),
            tenant_id=uuid.uuid4()
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_conv_msg_cache_hit_skips_db_lookup(self, chat_service, test_conversation, message_create_data, current_user):
        test_conversation.is_closed = False
        cached = json.dumps({"id": str(test_conversation.id), "is_closed": False})
        chat_service.msg_repo.create_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        chat_service.conv_repo.get_by_id = AsyncMock()

        with patch("app.services.chat_service.rdb") as mock_rdb:
            mock_rdb.get = AsyncMock(return_value=cached)
            conv, message = await chat_service.conv_msg(message_create_data, current_user)

        chat_service.conv_repo.get_by_id.assert_not_called()
        assert conv.id == str(test_conversation.id)

    @pytest.mark.asyncio
    async def test_conv_msg_not_found_raises(self, chat_service, message_create_data, current_user):
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=None)

        with patch("app.services.chat_service.rdb") as mock_rdb:
            mock_rdb.get = AsyncMock(return_value=None)
            with pytest.raises(ValueError):
                await chat_service.conv_msg(message_create_data, current_user)

    @pytest.mark.asyncio
    async def test_conv_msg_reopens_closed_conversation(self, chat_service, test_conversation, message_create_data, current_user):
        test_conversation.is_closed = True
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.conv_repo.set_conversation_closed = AsyncMock()
        chat_service.msg_repo.create_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with patch("app.services.chat_service.rdb") as mock_rdb:
            mock_rdb.get = AsyncMock(return_value=None)
            mock_rdb.set = AsyncMock()
            await chat_service.conv_msg(message_create_data, current_user)

        chat_service.conv_repo.set_conversation_closed.assert_called_once_with(test_conversation.id, False)

    @pytest.mark.asyncio
    async def test_conv_msg_media_error_rolls_back(self, chat_service, test_conversation, current_user, message_create_data):
        test_conversation.is_closed = False
        message_create_data.media = [{"file_name": "a.png"}]
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.create_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        chat_service.media_repo.create = AsyncMock(side_effect=Exception("boom"))
        chat_service.db.rollback = AsyncMock()

        with patch("app.services.chat_service.rdb") as mock_rdb:
            mock_rdb.get = AsyncMock(return_value=None)
            mock_rdb.set = AsyncMock()
            await chat_service.conv_msg(message_create_data, current_user)

        chat_service.db.rollback.assert_called_once()


    # --- _init_sender ---
    @pytest.mark.asyncio
    async def test_init_sender_telegram_user_skips_channel_lookup(self, chat_service, test_conversation):
        with patch("app.services.chat_service.SenderFactory") as mock_factory:
            sender = MagicMock()
            mock_factory.get_sender.return_value = sender
            result = await chat_service._init_sender("telegram_user", test_conversation.id, tg_listener=MagicMock())

        sender.set_listener.assert_called_once()
        sender.set_conv_id.assert_called_once_with(test_conversation.id)
        assert result is sender

    @pytest.mark.asyncio
    async def test_init_sender_telegram_bot_sets_bot_token(self, chat_service, channel_acc):
        chat_service.conv_repo.get_channel_acc_by_conversation = AsyncMock(return_value=channel_acc)
        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"bot_token": "tok"})):
            sender = MagicMock()
            mock_factory.get_sender.return_value = sender
            result = await chat_service._init_sender("telegram_bot", uuid.uuid4())

        sender.set_bot_token.assert_called_once_with("tok")
        sender.set_line_id.assert_called_once_with(channel_acc.line_id)

    @pytest.mark.asyncio
    async def test_init_sender_other_channel_sets_creds(self, chat_service, channel_acc):
        chat_service.conv_repo.get_channel_acc_by_conversation = AsyncMock(return_value=channel_acc)
        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"api_token": "t"})):
            sender = MagicMock()
            mock_factory.get_sender.return_value = sender
            await chat_service._init_sender("whatsapp_green", uuid.uuid4())

        sender.set_creds.assert_called_once_with({"api_token": "t"})

    # --- _process_queue_outgoing ---
    @pytest.mark.asyncio
    async def test_process_queue_outgoing_success(self, chat_service, test_conversation, current_user):
        message = MagicMock()
        message.id = 1
        message.conversation_id = test_conversation.id
        message.channel_msg_id = "ext-1"
        message.text = "hi"
        message.created_at = datetime.now(timezone.utc)
        message.media = []
        message.direction = "outbound"
        message.status = "sent"
        message.raw_content = {}
        message.user_id = None
        message.user_email = None
        message.user_full_name = None

        data = MagicMock(message_id=message.id, conversation_id=test_conversation.id, phone=None, media=None)
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service._finalize_message = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
                patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_new_message = AsyncMock()
            sender = MagicMock()
            sender.send = AsyncMock(return_value={"message_id": "x"})
            sender.extract_msg_id.return_value = "x"
            mock_init_sender.return_value = sender

            result = await chat_service._process_queue_outgoing("telegram_bot", data, current_user)

        assert data.phone == test_conversation.client_phone
        mock_manager.send_new_message.assert_called_once()
        chat_service._finalize_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_queue_outgoing_connect_error_notifies(self, chat_service, test_message, test_conversation, current_user):
        data = MagicMock(message_id=test_message.id, conversation_id=test_conversation.id, phone="+1", media=None)
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=test_message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service._finalize_message = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch("app.services.chat_service.notify_connection_error", new=AsyncMock()) as mock_notify, \
             patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_new_message = AsyncMock()
            sender = MagicMock()
            sender.send = AsyncMock(side_effect=httpx.ConnectError("fail"))
            sender.extract_msg_id.return_value = None
            mock_init_sender.return_value = sender

            await chat_service._process_queue_outgoing("whatsapp_green", data, current_user)

        mock_notify.assert_called_once_with(test_conversation.line_id, "whatsapp_green", chat_service.db)

    # --- create_msg_* delegation ---
    @pytest.mark.parametrize("method,channel", [
        ("create_msg_telegram_bot", "telegram_bot"),
        ("create_msg_whatsapp_green", "whatsapp_green"),
        ("create_msg_waba", "waba"),
        ("create_msg_vk", "vk"),
    ])
    @pytest.mark.asyncio
    async def test_create_msg_delegates_to_process_queue(self, chat_service, current_user, method, channel):
        chat_service._process_queue_outgoing = AsyncMock(return_value="ok")
        data = MagicMock()
        result = await getattr(chat_service, method)(data, current_user=current_user)

        chat_service._process_queue_outgoing.assert_called_once_with(channel, data, current_user)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_create_msg_telegram_user_passes_listener(self, chat_service, current_user):
        chat_service._process_queue_outgoing = AsyncMock(return_value="ok")
        data = MagicMock()
        listener = MagicMock()
        await chat_service.create_msg_telegram_user(data, current_user=current_user)

        chat_service._process_queue_outgoing.assert_called_once_with("telegram_user", data, current_user, tg_listener=listener)

    # --- edit_message ---
    @pytest.mark.asyncio
    async def test_edit_message_success(self, chat_service, test_message, test_conversation, current_user):
        test_conversation.channel_type = "vk"
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=test_message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.update = AsyncMock()
        chat_service.db.commit = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_message_update = AsyncMock()
            sender = MagicMock()
            sender.edit = AsyncMock()
            mock_init_sender.return_value = sender

            await chat_service.edit_message(test_message.id, "new text", current_user, tg_listener=None)

        sender.edit.assert_called_once_with(test_message.channel_msg_id, test_conversation.client_phone, "new text")
        chat_service.msg_repo.update.assert_called_once_with(test_message, text="new text")

    @pytest.mark.asyncio
    async def test_edit_message_not_found_404(self, chat_service, current_user):
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await chat_service.edit_message(uuid.uuid4(), "t", current_user, tg_listener=None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_message_no_channel_msg_id_400(self, chat_service, test_message, current_user):
        test_message.channel_msg_id = None
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=test_message)
        with pytest.raises(HTTPException) as exc:
            await chat_service.edit_message(test_message.id, "t", current_user, tg_listener=None)
        assert exc.value.status_code == 400

    # --- delete_message ---
    @pytest.mark.asyncio
    async def test_delete_message_success(self, chat_service, test_message, test_conversation, current_user):
        test_conversation.channel_type = "vk"
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=test_message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.delete = AsyncMock()
        chat_service.db.commit = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_message_update = AsyncMock()
            sender = MagicMock()
            sender.delete = AsyncMock()
            mock_init_sender.return_value = sender

            await chat_service.delete_message(test_message.id, current_user, tg_listener=None)

        sender.delete.assert_called_once_with(test_message.channel_msg_id, test_conversation.client_phone)
        chat_service.msg_repo.delete.assert_called_once_with(test_message)

    @pytest.mark.asyncio
    async def test_delete_message_not_found_404(self, chat_service, current_user):
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await chat_service.delete_message(uuid.uuid4(), current_user, tg_listener=None)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_message_no_channel_msg_id_400(self, chat_service, test_message, current_user):
        test_message.channel_msg_id = None
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=test_message)
        with pytest.raises(HTTPException) as exc:
            await chat_service.delete_message(test_message.id, current_user, tg_listener=None)
        assert exc.value.status_code == 400

    # --- get_conversations (full, with rows) ---
    @pytest.mark.asyncio
    async def test_get_conversations_no_tenants_returns_empty(self, chat_service):
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[])
        result = await chat_service.get_conversations(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_conversations_builds_list(self, chat_service, test_conversation):
        tenant = MagicMock(id=uuid.uuid4(), name="T1")
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[tenant])
        chat_service.conv_repo.get_conversations_with_stats = AsyncMock(
            return_value=[(test_conversation, "line1", tenant.id, 2, datetime.now(timezone.utc))]
        )
        chat_service.msg_repo.get_last_message = AsyncMock(return_value=None)

        result = await chat_service.get_conversations(tenant.id)
        assert len(result) == 1

    # --- get_conversations_filtered ---
    @pytest.mark.asyncio
    async def test_get_conversations_filtered_no_tenants(self, chat_service):
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[])
        result = await chat_service.get_conversations_filtered(uuid.uuid4())
        assert result == []

    # --- get_lines_with_available_channels ---
    @pytest.mark.asyncio
    async def test_get_lines_with_available_channels(self, chat_service):
        tenant = MagicMock(id=uuid.uuid4())
        tenant.name = "T1"
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[tenant])
        row = MagicMock(id=uuid.uuid4())
        row.name = "Line1"
        row.channel_type = "vk"
        chat_service.conv_repo.get_lines_with_available_channels = AsyncMock(return_value=[row])

        result = await chat_service.get_lines_with_available_channels(uuid.uuid4())
        assert len(result) == 1
        assert result[0].channels[0].channel_type == "vk"

    # --- get_conversation ---
    @pytest.mark.asyncio
    async def test_get_conversation_returns_none_when_missing(self, chat_service):
        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=None)
        result = await chat_service.get_conversation(uuid.uuid4(), uuid.uuid4())
        assert result is None

    # --- create_conversation ---
    @pytest.mark.asyncio
    async def test_create_conversation_telegram_user_starts_listening(self, chat_service, test_conversation):
        data = MagicMock(line_id=uuid.uuid4(), channel_type="telegram_user", crm_chat_id=None, client_phone="+1", meta={})
        chat_service.conv_repo.create_conversation = AsyncMock(return_value=test_conversation)
        tg_acc = MagicMock(channel_type=MagicMock(value="telegram_user"), phone="+7999")
        chat_service.ch_acc_repo.get_by_line = AsyncMock(return_value=[tg_acc])
        listener = MagicMock()
        listener.start_listening = AsyncMock()

        await chat_service.create_conversation(uuid.uuid4(), data, tg_listener=listener)

        listener.start_listening.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_conversation_no_telegram_acc_logs_warning(self, chat_service, test_conversation):
        data = MagicMock(line_id=uuid.uuid4(), channel_type="telegram_user", crm_chat_id=None, client_phone="+1", meta={})
        chat_service.conv_repo.create_conversation = AsyncMock(return_value=test_conversation)
        chat_service.ch_acc_repo.get_by_line = AsyncMock(return_value=[])
        listener = MagicMock()
        listener.start_listening = AsyncMock()

        result = await chat_service.create_conversation(uuid.uuid4(), data, tg_listener=listener)

        listener.start_listening.assert_not_called()
        assert result is not None

    # --- _finalize_message ---
    @pytest.mark.asyncio
    async def test_finalize_message_success_updates_and_sends_status(self, chat_service, test_message):
        data = MagicMock(raw_content={}, media=None)
        with patch("app.services.chat_service.manager") as mock_manager:
            mock_manager.send_message_status = AsyncMock()
            await chat_service._finalize_message(
                message=test_message, conversation_id=uuid.uuid4(), channel_type="vk",
                data=data, current_user=MagicMock(), success=True,
                channel_msg_id="ext-2", raw_content={"a": 1},
            )
        mock_manager.send_message_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_message_status_error_is_swallowed(self, chat_service, test_message):
        data = MagicMock(raw_content={}, media=None)
        with patch("app.services.chat_service.manager") as mock_manager:
            mock_manager.send_message_status = AsyncMock(side_effect=Exception("ws down"))
            await chat_service._finalize_message(
                message=test_message, conversation_id=uuid.uuid4(), channel_type="vk",
                data=data, current_user=MagicMock(), success=True,
            )
        # не должно падать наружу

    @pytest.mark.asyncio
    async def test_finalize_message_failure_skips_update(self, chat_service, test_message):
        chat_service.msg_repo.update = AsyncMock()
        data = MagicMock(raw_content={}, media=None)
        with patch("app.services.chat_service.manager") as mock_manager:
            mock_manager.send_message_status = AsyncMock()
            await chat_service._finalize_message(
                message=test_message, conversation_id=uuid.uuid4(), channel_type="vk",
                data=data, current_user=MagicMock(), success=False,
            )
        chat_service.msg_repo.update.assert_not_called()

    # --- clean_raw_content ---
    def test_clean_raw_content_datetime(self, chat_service):
        d = datetime.now(timezone.utc)
        assert chat_service.clean_raw_content(d) == d.isoformat()

    def test_clean_raw_content_bytes(self, chat_service):
        assert chat_service.clean_raw_content(b"abc") == base64.b64encode(b"abc").decode("ascii")

    def test_clean_raw_content_nested(self, chat_service):
        d = datetime.now(timezone.utc)
        result = chat_service.clean_raw_content({"a": [d, b"x"]})
        assert result["a"][0] == d.isoformat()
        assert result["a"][1] == base64.b64encode(b"x").decode("ascii")

    # --- save_incoming_* ---
    @pytest.mark.asyncio
    async def test_save_incoming_message(self, chat_service, test_message):
        event = MagicMock()
        event.message.text = "hey"
        event.message.id = 123
        event.message.date = datetime.now(timezone.utc)
        chat_service.conv_msg = AsyncMock(return_value=(MagicMock(), test_message))

        result = await chat_service.save_incoming_message(uuid.uuid4(), "+1", event)
        chat_service.conv_msg.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_save_incoming_green_downloads_file(self, chat_service, test_message):
        chat_service.conv_msg = AsyncMock(return_value=(MagicMock(), test_message))
        chat_service.storage.save_file = AsyncMock()

        with patch("app.services.chat_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock(content=b"filedata")
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await chat_service.save_incoming_green(
                uuid.uuid4(), {"idMessage": "m1"}, media_id=uuid.uuid4(),
                file_url="http://x/file", mime_type="image/png",
            )

        chat_service.storage.save_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_incoming_waba(self, chat_service, test_message):
        chat_service.conv_msg = AsyncMock(return_value=(MagicMock(), test_message))
        await chat_service.save_incoming_waba(uuid.uuid4(), "ext-3", "hi")
        chat_service.conv_msg.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_incoming_vk(self, chat_service, test_message):
        chat_service.conv_msg = AsyncMock(return_value=(MagicMock(), test_message))
        await chat_service.save_incoming_vk(uuid.uuid4(), "ext-4", "hi", "text")
        chat_service.conv_msg.assert_called_once()

    # --- close_or_open_conversation ---
    @pytest.mark.asyncio
    async def test_close_or_open_conversation_not_found(self, chat_service):
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[])
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await chat_service.close_or_open_conversation(uuid.uuid4(), True, uuid.uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_close_or_open_conversation_forbidden(self, chat_service, test_conversation):
        tenant = MagicMock(id=uuid.uuid4())
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[tenant])
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        line = MagicMock(tenant_id=uuid.uuid4())
        chat_service.line_repo.get_by_id = AsyncMock(return_value=line)
        with pytest.raises(HTTPException) as exc:
            await chat_service.close_or_open_conversation(test_conversation.id, True, uuid.uuid4())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_close_or_open_conversation_success(self, chat_service, test_conversation):
        tenant = MagicMock(id=uuid.uuid4())
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[tenant])
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        line = MagicMock(tenant_id=tenant.id)
        chat_service.line_repo.get_by_id = AsyncMock(return_value=line)
        chat_service.conv_repo.set_conversation_closed = AsyncMock(return_value=test_conversation)
        chat_service.db.commit = AsyncMock()

        result = await chat_service.close_or_open_conversation(test_conversation.id, True, uuid.uuid4())
        assert result is test_conversation

    # --- save_crm_incoming ---
    @pytest.mark.asyncio
    async def test_save_crm_incoming_conv_not_found(self, chat_service):
        data = MagicMock(line_id=uuid.uuid4(), crm_chat_id="c1")
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[])
        result = await chat_service.save_crm_incoming(data)
        assert result == {"status": "not_found"}

    @pytest.mark.asyncio
    async def test_save_crm_incoming_success(self, chat_service, test_conversation, test_message, channel_acc):
        data = MagicMock(line_id=uuid.uuid4(), crm_chat_id="c1", text="hi", raw_content={}, media=[])
        test_conversation.channel_type = "vk"
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        chat_service.msg_repo.create = AsyncMock(return_value=test_message)
        chat_service.conv_repo.get_channel_acc_by_conversation = AsyncMock(return_value=channel_acc)

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"bot_token": "t"})):
            mock_manager.send_new_message = AsyncMock()
            result = await chat_service.save_crm_incoming(data)

        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_save_crm_incoming_telegram_bot_sends(self, chat_service, test_conversation, test_message, channel_acc):
        data = MagicMock(line_id=uuid.uuid4(), crm_chat_id="c1", text="hi", raw_content={}, media=[])
        test_conversation.channel_type = "telegram_bot"
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        chat_service.msg_repo.create = AsyncMock(return_value=test_message)
        chat_service.conv_repo.get_channel_acc_by_conversation = AsyncMock(return_value=channel_acc)

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"bot_token": "t"})), \
             patch("app.senders.telegram_bot.TelegramBotSender") as mock_sender_cls:
            mock_manager.send_new_message = AsyncMock()
            sender = MagicMock()
            sender.send = AsyncMock()
            mock_sender_cls.return_value = sender

            result = await chat_service.save_crm_incoming(data)

        sender.send.assert_called_once()
        assert result == {"status": "ok"}

    # --- start_crm_outgoing ---
    @pytest.mark.asyncio
    async def test_start_crm_outgoing_existing_conv_with_crm_chat_id(self, chat_service, test_conversation):
        data = MagicMock(line_id=uuid.uuid4(), client_phone="+1")
        test_conversation.crm_chat_id = "dc_1"
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])

        result = await chat_service.start_crm_outgoing(data)
        assert result == {"status": "exists", "conversation_id": str(test_conversation.id)}

    @pytest.mark.asyncio
    async def test_start_crm_outgoing_no_channel_found(self, chat_service, test_conversation):
        data = MagicMock(line_id=uuid.uuid4(), client_phone="+1", channel_account_id=None, channel_type="vk")
        test_conversation.crm_chat_id = None
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        chat_service.ch_acc_repo.get_multi = AsyncMock(return_value=[])

        result = await chat_service.start_crm_outgoing(data)
        assert result == {"error": "Канал не найден"}

    @pytest.mark.asyncio
    async def test_start_crm_outgoing_creates_conv_and_sends(self, chat_service, channel_acc):
        data = MagicMock(line_id=uuid.uuid4(), client_phone="+1", channel_account_id=None,
                          channel_type="vk", crm_connection_id="cc1", text="hi")
        new_conv = MagicMock(id=uuid.uuid4())
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[])
        chat_service.conv_repo.create = AsyncMock(return_value=new_conv)
        channel_acc.channel_type = "vk"
        chat_service.ch_acc_repo.get_multi = AsyncMock(return_value=[channel_acc])

        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"api_token": "t"})):
            sender = MagicMock()
            sender.send = AsyncMock()
            mock_factory.get_sender.return_value = sender

            result = await chat_service.start_crm_outgoing(data)

        assert result == {"status": "ok", "conversation_id": str(new_conv.id)}

    # --- robot_send ---
    @pytest.mark.asyncio
    async def test_robot_send_no_channel_found(self, chat_service, test_conversation):
        data = MagicMock(line_id=uuid.uuid4(), client_phone="+1", channel_account_id=None, channel_type="vk")
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        chat_service.ch_acc_repo.get_multi = AsyncMock(return_value=[])

        result = await chat_service.robot_send(data)
        assert result == {"error": "Канал не найден"}

    @pytest.mark.asyncio
    async def test_robot_send_success_with_media(self, chat_service, test_conversation, test_message, channel_acc):
        data = MagicMock(
            line_id=uuid.uuid4(), client_phone="+1", channel_account_id=None,
            channel_type="vk", crm_connection_id="cc1", text="hi",
            media=[{"id": str(uuid.uuid4()), "file_name": "f.png", "mime_type": "image/png"}],
        )
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        channel_acc.channel_type = "vk"
        chat_service.ch_acc_repo.get_multi = AsyncMock(return_value=[channel_acc])
        chat_service.msg_repo.create = AsyncMock(return_value=test_message)
        chat_service.media_repo.create = AsyncMock()

        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"api_token": "t"})):
            sender = MagicMock()
            sender.send = AsyncMock()
            mock_factory.get_sender.return_value = sender

            result = await chat_service.robot_send(data)

        chat_service.media_repo.create.assert_called_once()
        assert result["status"] == "ok"


# --- get_messages (полный путь) ---
    @pytest.mark.asyncio
    async def test_get_messages_full_path_with_media_and_user(self, chat_service, test_conversation):
        msg = MagicMock()
        msg.id = 1
        msg.conversation_id = test_conversation.id
        msg.channel_msg_id = "ext-1"
        msg.direction = MessageDirection.inbound
        msg.status = MessageStatus.sent
        msg.text = "hi"
        msg.raw_content = {"file_name": "a.png"}
        msg.created_at = datetime.now(timezone.utc)
        msg.user = MagicMock(email="u@test.com", full_name="User Name")
        msg.user_id = uuid.uuid4()

        media_item = MagicMock()
        media_item.id = uuid.uuid4()
        media_item.file_name = "a.png"
        media_item.mime_type = "image/png"
        msg.media = [media_item]
        msg.__dict__.update({
            "id": 1, "conversation_id": test_conversation.id, "channel_msg_id": "ext-1",
            "direction": MessageDirection.inbound, "status": MessageStatus.sent,
            "text": "hi", "raw_content": {"file_name": "a.png"},
            "created_at": msg.created_at, "user_id": msg.user_id,
        })

        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.get_conversation_messages = AsyncMock(return_value=[msg])
        chat_service.storage.presigned_url = MagicMock(return_value="http://url")

        result = await chat_service.get_messages(test_conversation.id, uuid.uuid4())

        assert len(result) == 1
        assert result[0].user_email == "u@test.com"
        assert result[0].media[0].file_name == "a.png"

    @pytest.mark.asyncio
    async def test_get_messages_extracts_filename_from_green_payload(self, chat_service, test_conversation):
        msg = MagicMock()
        msg.user = None
        raw = {"messageData": {"fileMessageData": {"fileName": "green.png"}}}
        msg.__dict__.update({
            "id": 1, "conversation_id": test_conversation.id, "channel_msg_id": "ext-2",
            "direction": MessageDirection.inbound, "status": MessageStatus.sent,
            "text": None, "raw_content": raw,
            "created_at": datetime.now(timezone.utc), "user_id": None,
        })
        msg.raw_content = raw
        msg.media = []

        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.get_conversation_messages = AsyncMock(return_value=[msg])

        result = await chat_service.get_messages(test_conversation.id, uuid.uuid4())

        assert len(result) == 1
        assert result[0].text is None

    # --- get_conversation (happy path) ---
    @pytest.mark.asyncio
    async def test_get_conversation_happy_path(self, chat_service, test_conversation):
        test_conversation.__dict__.update({
            "id": test_conversation.id, "line_id": test_conversation.line_id,
            "channel_type": "vk", "crm_chat_id": "c1", "client_phone": "+1",
            "meta": {}, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=test_conversation)
        chat_service.msg_repo.get_conversation_messages = AsyncMock(return_value=[])
        chat_service.conv_repo.get_line_phone_by_conversation = AsyncMock(return_value="+79990001122")

        result = await chat_service.get_conversation(test_conversation.id, uuid.uuid4())

        assert result.my_phone == "+79990001122"
        assert result.messages == []

    # --- _save_uploaded_file ---
    @pytest.mark.asyncio
    async def test_save_uploaded_file(self, chat_service):
        media_id = uuid.uuid4()
        file = MagicMock()
        file.read = AsyncMock(return_value=b"data")
        file.filename = "a.png"
        file.content_type = "image/png"
        chat_service.storage.save_file = AsyncMock(return_value={"id": str(media_id)})

        result = await chat_service._save_uploaded_file(file, media_id)

        chat_service.storage.save_file.assert_called_once_with(b"data", media_id, "a.png", "image/png")
        assert result == {"id": str(media_id)}


# --- _process_queue_outgoing с media ---
    @pytest.mark.asyncio
    async def test_process_queue_outgoing_with_media_commits_and_refreshes(self, chat_service, test_conversation, current_user):
        message = MagicMock()
        message.id = 1
        message.conversation_id = test_conversation.id
        message.text = "hi"
        message.created_at = datetime.now(timezone.utc)
        message.media = []
        message.channel_msg_id = None
        message.direction = "outbound"
        message.status = "sent"
        message.raw_content = {}
        message.user_id = None
        message.user_email = None
        message.user_full_name = None

        data = MagicMock(
            message_id=message.id, conversation_id=test_conversation.id,
            phone="+1", media=[{"id": str(uuid.uuid4()), "file_name": "a.png"}],
        )
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.media_repo.create = AsyncMock()
        chat_service.db.commit = AsyncMock()
        chat_service.db.refresh = AsyncMock()
        chat_service._finalize_message = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_new_message = AsyncMock()
            sender = MagicMock()
            sender.send = AsyncMock(return_value={"message_id": "x"})
            sender.extract_msg_id.return_value = "x"
            mock_init_sender.return_value = sender

            await chat_service._process_queue_outgoing("vk", data, current_user)

        chat_service.media_repo.create.assert_called_once()
        chat_service.db.commit.assert_called_once()
        chat_service.db.refresh.assert_called_once_with(message, attribute_names=["media"])

    @pytest.mark.asyncio
    async def test_process_queue_outgoing_media_error_rolls_back(self, chat_service, test_conversation, current_user):
        message = MagicMock()
        message.id = 1
        message.conversation_id = test_conversation.id
        message.text = "hi"
        message.created_at = datetime.now(timezone.utc)
        message.media = []
        message.channel_msg_id = None
        message.direction = "outbound"
        message.status = "sent"
        message.raw_content = {}
        message.user_id = None
        message.user_email = None
        message.user_full_name = None

        data = MagicMock(
            message_id=message.id, conversation_id=test_conversation.id,
            phone="+1", media=[{"id": str(uuid.uuid4()), "file_name": "a.png"}],
        )
        chat_service.msg_repo.get_by_id = AsyncMock(return_value=message)
        chat_service.conv_repo.get_by_id = AsyncMock(return_value=test_conversation)
        chat_service.media_repo.create = AsyncMock(side_effect=Exception("boom"))
        chat_service.db.rollback = AsyncMock()
        chat_service.db.commit = AsyncMock()
        chat_service.db.refresh = AsyncMock()
        chat_service._finalize_message = AsyncMock()

        with patch("app.services.chat_service.manager") as mock_manager, \
             patch.object(chat_service, "_init_sender", new=AsyncMock()) as mock_init_sender:
            mock_manager.send_new_message = AsyncMock()
            sender = MagicMock()
            sender.send = AsyncMock(return_value={"message_id": "x"})
            sender.extract_msg_id.return_value = "x"
            mock_init_sender.return_value = sender

            await chat_service._process_queue_outgoing("vk", data, current_user)

        chat_service.db.rollback.assert_called_once()

    # --- get_conversations_filtered happy path ---
    @pytest.mark.asyncio
    async def test_get_conversations_filtered_builds_list(self, chat_service, test_conversation):
        tenant = MagicMock(id=uuid.uuid4())
        chat_service.tenant_repo.get_all_tenants = AsyncMock(return_value=[tenant])
        chat_service.conv_repo.get_conversations_with_filters = AsyncMock(
            return_value=[(test_conversation, "line1", tenant.id, 0, None)]
        )

        result = await chat_service.get_conversations_filtered(tenant.id, is_closed=False)

        assert len(result) == 1
        assert result[0].last_message is None

    # --- save_incoming_green без file_url ---
    @pytest.mark.asyncio
    async def test_save_incoming_green_without_file_url(self, chat_service, test_message):
        chat_service.conv_msg = AsyncMock(return_value=(MagicMock(), test_message))
        chat_service.storage.save_file = AsyncMock()

        await chat_service.save_incoming_green(
            uuid.uuid4(), {"idMessage": "m1"}, text="hi",
        )

        chat_service.storage.save_file.assert_not_called()
        chat_service.conv_msg.assert_called_once()

    # --- start_crm_outgoing с channel_account_id ---
    @pytest.mark.asyncio
    async def test_start_crm_outgoing_uses_channel_account_id(self, chat_service, channel_acc):
        data = MagicMock(
            line_id=uuid.uuid4(), client_phone="+1", channel_account_id=uuid.uuid4(),
            channel_type="vk", crm_connection_id="cc1", text="hi",
        )
        new_conv = MagicMock(id=uuid.uuid4())
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[])
        chat_service.conv_repo.create = AsyncMock(return_value=new_conv)
        channel_acc.channel_type = "vk"
        chat_service.ch_acc_repo.get_by_id = AsyncMock(return_value=channel_acc)
        chat_service.ch_acc_repo.get_multi = AsyncMock()

        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"api_token": "t"})):
            sender = MagicMock()
            sender.send = AsyncMock()
            mock_factory.get_sender.return_value = sender

            await chat_service.start_crm_outgoing(data)

        chat_service.ch_acc_repo.get_by_id.assert_called_once_with(data.channel_account_id)
        chat_service.ch_acc_repo.get_multi.assert_not_called()

    # --- robot_send с channel_account_id ---
    @pytest.mark.asyncio
    async def test_robot_send_uses_channel_account_id(self, chat_service, test_conversation, test_message, channel_acc):
        data = MagicMock(
            line_id=uuid.uuid4(), client_phone="+1", channel_account_id=uuid.uuid4(),
            channel_type="vk", crm_connection_id="cc1", text="hi", media=None,
        )
        chat_service.conv_repo.get_multi = AsyncMock(return_value=[test_conversation])
        channel_acc.channel_type = "vk"
        chat_service.ch_acc_repo.get_by_id = AsyncMock(return_value=channel_acc)
        chat_service.ch_acc_repo.get_multi = AsyncMock()
        chat_service.msg_repo.create = AsyncMock(return_value=test_message)

        with patch("app.services.chat_service.SenderFactory") as mock_factory, \
             patch("app.services.chat_service.decrypt", return_value=json.dumps({"api_token": "t"})):
            sender = MagicMock()
            sender.send = AsyncMock()
            mock_factory.get_sender.return_value = sender

            result = await chat_service.robot_send(data)

        chat_service.ch_acc_repo.get_by_id.assert_called_once_with(data.channel_account_id)
        assert result["status"] == "ok"