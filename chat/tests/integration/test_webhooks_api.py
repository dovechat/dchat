import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.api.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestWebhooksIntegration:

    @pytest.fixture
    def mock_green_listener(self):
        app.state.green_listener = MagicMock()
        app.state.green_listener.handle_webhook = AsyncMock()
        yield app.state.green_listener
        del app.state.green_listener

    @pytest.fixture
    def mock_waba_listener(self):
        app.state.waba_listener = MagicMock()
        app.state.waba_listener.handle_webhook = AsyncMock()
        yield app.state.waba_listener
        del app.state.waba_listener

    @pytest.fixture
    def mock_vk_listener(self):
        app.state.vk_listener = MagicMock()
        app.state.vk_listener.handle_webhook = AsyncMock(return_value="ok")
        yield app.state.vk_listener
        del app.state.vk_listener

    async def test_green_webhook_success(self, client, mock_green_listener):
        line_id = uuid.uuid4()
        payload = {"typeWebhook": "incomingMessageReceived"}

        resp = await client.post(f"/v1/webhooks/whatsapp/green/{line_id}", json=payload)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_green_listener.handle_webhook.assert_awaited_once_with(line_id, payload, None)

    async def test_green_webhook_invalid_line_id(self, client, mock_green_listener):
        resp = await client.post("/v1/webhooks/whatsapp/green/not-a-uuid", json={})

        assert resp.status_code == 422
        mock_green_listener.handle_webhook.assert_not_awaited()

    async def test_waba_webhook_success(self, client, mock_waba_listener):
        line_id = "some-line-id"
        token = "some-token"
        payload = {"entry": []}

        resp = await client.post(f"/v1/webhooks/whatsapp/waba/{line_id}/{token}", json=payload)

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_waba_listener.handle_webhook.assert_awaited_once_with(line_id, token, payload)

    async def test_vk_webhook_success(self, client, mock_vk_listener):
        line_id = uuid.uuid4()
        payload = {"type": "confirmation"}

        resp = await client.post(f"/v1/webhooks/vk/{line_id}", json=payload)

        assert resp.status_code == 200
        assert resp.text == "ok"
        mock_vk_listener.handle_webhook.assert_awaited_once_with(line_id, payload)

    async def test_vk_webhook_invalid_line_id(self, client, mock_vk_listener):
        resp = await client.post("/v1/webhooks/vk/not-a-uuid", json={})

        assert resp.status_code == 422
        mock_vk_listener.handle_webhook.assert_not_awaited()