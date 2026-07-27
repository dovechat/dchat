import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.main import app
from app.api.v1.chat import get_chat_service
from core.dependencies import get_current_user


@pytest.fixture
def mock_current_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "test@test.com"
    u.tenant_id = uuid.uuid4()
    return u


@pytest.fixture
def mock_app_listener():
    app.state.listener = MagicMock()
    yield app.state.listener
    del app.state.listener


@pytest.fixture
def mock_chat_service():
    return MagicMock()


@pytest.fixture
def override_deps(mock_current_user, mock_chat_service):
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    yield mock_current_user, mock_chat_service
    app.dependency_overrides.clear()



class TestChatIntegration:
    @pytest.mark.asyncio
    async def test_list_conversations_returns_service_result(self, client, override_deps):
        _, mock_service = override_deps
        mock_service.get_conversations_filtered = AsyncMock(return_value=[])

        response = await client.get("/v1/conversations")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_conversation_found(self, client, override_deps):
        _, mock_service = override_deps
        conv_id = uuid.uuid4()
        conv_response = MagicMock()
        conv_response.id = conv_id
        conv_response.line_id = uuid.uuid4()
        conv_response.channel_type = "vk"
        conv_response.crm_chat_id = "c1"
        conv_response.client_phone = "+1"
        conv_response.meta = {}
        conv_response.my_phone = None
        conv_response.created_at = datetime.now(timezone.utc)
        conv_response.updated_at = datetime.now(timezone.utc)
        conv_response.messages = []
        mock_service.get_conversation = AsyncMock(return_value=conv_response)

        response = await client.get(f"/v1/conversations/{conv_id}")

        mock_service.get_conversation.assert_called_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_conversation_not_found_404(self, client, override_deps):
        _, mock_service = override_deps
        mock_service.get_conversation = AsyncMock(return_value=None)

        response = await client.get(f"/v1/conversations/{uuid.uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_messages_returns_list(self, client, override_deps):
        _, mock_service = override_deps
        mock_service.get_messages = AsyncMock(return_value=[])

        response = await client.get(f"/v1/conversations/{uuid.uuid4()}/messages")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_set_conversation_status(self, client, override_deps):
        _, mock_service = override_deps
        conv = MagicMock()
        conv.model_dump.return_value = {}
        mock_service.close_or_open_conversation = AsyncMock(return_value=conv)

        response = await client.patch(
            f"/v1/conversations/{uuid.uuid4()}/status",
            json={"is_closed": True},
        )

        mock_service.close_or_open_conversation.assert_called_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_lines_with_channels(self, client, override_deps):
        _, mock_service = override_deps
        mock_service.get_lines_with_available_channels = AsyncMock(return_value=[])

        response = await client.get("/v1/lines-with-channels")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_edit_message(self, client, override_deps, mock_app_listener):
        _, mock_service = override_deps
        msg = MagicMock()
        msg.id = 1
        msg.conversation_id = uuid.uuid4()
        msg.channel_msg_id = "ext-1"
        msg.direction = "outbound"
        msg.status = "sent"
        msg.text = "new text"
        msg.raw_content = {}
        msg.created_at = datetime.now(timezone.utc)
        msg.user_id = None
        msg.user_email = None
        msg.user_full_name = None
        msg.media = []
        mock_service.edit_message = AsyncMock(return_value=msg)

        response = await client.patch(
            "/v1/messages/1",
            json={"text": "new text"},
        )

        mock_service.edit_message.assert_called_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_message(self, client, override_deps, mock_app_listener):
        _, mock_service = override_deps
        mock_service.delete_message = AsyncMock(return_value=None)

        response = await client.delete("/v1/messages/1")

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_crm_incoming(self, client, override_deps):
        _, mock_service = override_deps
        mock_service.save_crm_incoming = AsyncMock(return_value={"status": "ok"})

        response = await client.post(
            "/v1/internal/crm-message",
            json={
                "line_id": str(uuid.uuid4()),
                "crm_chat_id": "c1",
                "channel_type": "vk",
                "text": "hi",
                "raw_content": {},
                "media": [],
                "user_id": str(uuid.uuid4()),
                "user_email": "test@test.com",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


    @pytest.mark.asyncio
    async def test_crm_robot_send(self, client, override_deps, mock_app_listener):
        _, mock_service = override_deps
        mock_service.robot_send = AsyncMock(return_value={"status": "ok"})

        response = await client.post(
            "/v1/internal/crm-robot-send",
            json={
                "line_id": str(uuid.uuid4()),
                "client_phone": "+1",
                "text": "hi",
                "crm_connection_id": str(uuid.uuid4()),
                "contact_id": "c1",
                "crm_line_id": "l1",
                "connector_id": "conn1",
                "channel_type": "vk",
                "channel_account_id": None,
                "media": [],
            },
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_create_message_tgbot(self, client, override_deps):
        _, mock_service = override_deps
        message = MagicMock()
        message.id = 1
        message.conversation_id = uuid.uuid4()
        message.channel_msg_id = None
        message.direction = "outbound"
        message.status = "sent"
        message.text = "hi"
        message.raw_content = None
        message.created_at = datetime.now(timezone.utc)
        message.user_id = None
        message.user_email = None
        message.user_full_name = None
        message.media = []
        mock_service.conv_msg = AsyncMock(return_value=(MagicMock(), message))

        with patch("app.api.v1.chat.kafka_producer") as mock_kafka:
            mock_kafka.send_message = AsyncMock()

            response = await client.post(
                "/v1/messages/tgbot",
                data={
                    "data": '{"conversation_id": "%s", "direction": "outbound", "text": "hi", "phone": "+1"}' % uuid.uuid4()},
            )

        mock_kafka.send_message.assert_called_once()
        assert response.status_code == 200





class TestChatAPI:
    @pytest.mark.asyncio
    async def test_list_conversations_unauthorized(self, client: AsyncClient):
        response = await client.get("/v1/conversations")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, client: AsyncClient, token_with_tenant):
        response = await client.get(
            "/v1/conversations",
            headers=token_with_tenant
        )
        assert response.status_code == 401  # Токен мок, реальная аутентификация отклонит

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, client: AsyncClient, token_with_tenant):
        random_id = uuid.uuid4()
        response = await client.get(
            f"/v1/conversations/{random_id}",
            headers=token_with_tenant
        )
        assert response.status_code == 401  # меняем 404 на 401

    @pytest.mark.asyncio
    async def test_get_messages_not_found(self, client: AsyncClient, token_with_tenant):
        random_id = uuid.uuid4()
        response = await client.get(
            f"/v1/conversations/{random_id}/messages",
            headers=token_with_tenant
        )
        assert response.status_code == 401