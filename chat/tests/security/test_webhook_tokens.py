import pytest

pytestmark = pytest.mark.asyncio


class TestWebhookTokenVerification:

    # --- Telegram bot ---
    # curl -i -X POST 'https://dev.dove-chat.pro/api/v1/bot/webhook/{line_id}' \
    #   -H 'x-telegram-bot-api-secret-token: <token>'

    async def test_tg_bot_webhook_invalid_secret_token_403(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1, "is_bot": False, "first_name": "a"},
                "chat": {"id": 1, "type": "private"},
                "date": 1784646702,
                "text": "test",
            },
        }
        resp = await client.post(
            f"/v1/bot/webhook/{line_id}",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": "WRONG_TOKEN"},
        )
        assert resp.status_code == 403

    async def test_tg_bot_webhook_valid_secret_token_200(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1, "is_bot": False, "first_name": "a"},
                "chat": {"id": 1, "type": "private"},
                "date": 1784646702,
                "text": "test",
            },
        }
        resp = await client.post(
            f"/v1/bot/webhook/{line_id}",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": "ibe4b9Mx9-JXS56s0O7OGRhljSyIZNwKEylInvvboY0"},
        )
        assert resp.status_code == 200

    # --- WABA ---
    # curl -i -X POST 'https://dev.dove-chat.pro/api/v1/webhooks/whatsapp/waba/{line_id}/{token}'

    async def test_waba_webhook_invalid_token_403(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        resp = await client.post(
            f"/webhooks/whatsapp/waba/{line_id}/WRONG_TOKEN",
            json={"entry": []},
        )
        assert resp.status_code == 403

    async def test_waba_webhook_valid_token_200(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        token = "OL9CKLBz16rcMJHsPVHFHr6rMqkzSjgYe6Aua5whAO"
        resp = await client.post(
            f"/webhooks/whatsapp/waba/{line_id}/{token}",
            json={"entry": []},
        )
        assert resp.status_code == 200

    # --- Green ---
    # header name/value not confirmed from a real curl in this chat — placeholder, проверь сам

    async def test_green_webhook_invalid_bearer_403(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        resp = await client.post(
            f"/webhooks/whatsapp/green/{line_id}",
            json={"typeWebhook": "incomingMessageReceived"},
            headers={"Authorization": "Bearer WRONG_TOKEN"},
        )
        assert resp.status_code in (401, 403)

    async def test_green_webhook_valid_bearer_200(self, client):
        line_id = "5cdb55c0-4292-44b1-8782-9c5f9d908eeb"
        resp = await client.post(
            f"/webhooks/whatsapp/green/{line_id}",
            json={"typeWebhook": "incomingMessageReceived"},
            headers={"Authorization": "Bearer 89vn3jsdx90dsw269sz2sf7e5wrtc78sds"},
        )
        assert resp.status_code == 200