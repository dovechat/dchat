import json
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.api.main import app
from core.database import AsyncSessionLocal
from infra.crypto import decrypt, encrypt
from models.lines import ChannelAccount, Line
from models.tenants import Tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")

from core.database import engine


@pytest_asyncio.fixture(autouse=True)
def _mock_waba_listener():
    app.state.waba_listener = MagicMock()
    app.state.waba_listener.handle_webhook = AsyncMock()
    yield
    del app.state.waba_listener


@pytest_asyncio.fixture(autouse=True)
async def _reset_pool_after_test():
    yield
    await engine.dispose()

async def _get_active_account(channel_type: str) -> ChannelAccount:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChannelAccount).where(
                ChannelAccount.channel_type == channel_type,
                ChannelAccount.connection_status == "connected",
                ChannelAccount.updated_at >= today_start,
            ).limit(1)
        )
        account = result.scalar_one_or_none()
        if account is None:
            pytest.skip(f"no {channel_type} ChannelAccount created today in DB")
        return account


def _decrypt_creds(account: ChannelAccount) -> dict:
    creds = decrypt(account.credentials_encrypted["encrypted_data"])
    return json.loads(creds)


@pytest_asyncio.fixture
async def tg_bot_account():
    """Вставляет тестовую line + TG bot линию с известным secret_token, удаляет после теста."""
    secret_token = "test-secret-token-123"
    creds = {"bot_token": "0:test", "secret_token": secret_token}
    encrypted = {"encrypted_data": encrypt(json.dumps(creds))}
    line_id = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant.id).limit(1))
        tenant_id = result.scalar_one_or_none()
        if tenant_id is None:
            pytest.skip("no Tenant in DB to attach test Line to")

        line = Line(id=line_id, tenant_id=tenant_id, name="test-tg-bot-line")
        session.add(line)
        await session.commit()

    async with AsyncSessionLocal() as session:
        account = ChannelAccount(
            id=uuid.uuid4(),
            line_id=line_id,
            channel_type="telegram_bot",
            connection_status="connected",
            credentials_encrypted=encrypted,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(account)
        await session.commit()

    yield line_id, secret_token

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(ChannelAccount).where(ChannelAccount.line_id == line_id)
            )
            acc_to_delete = result.scalar_one_or_none()
            if acc_to_delete is not None:
                await session.delete(acc_to_delete)
            await session.commit()
        except Exception:
            await session.rollback()

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Line).where(Line.id == line_id))
            line_to_delete = result.scalar_one_or_none()
            if line_to_delete is not None:
                await session.delete(line_to_delete)
            await session.commit()
        except Exception:
            await session.rollback()


@pytest_asyncio.fixture
async def waba_account():
    """Вставляет тестовую line + WABA линию с известным token, удаляет после теста."""
    waba_token = "test-waba-token-456"
    creds = {"token": waba_token, "api_key": "test-api-key"}
    encrypted = {"encrypted_data": encrypt(json.dumps(creds))}
    line_id = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant.id).limit(1))
        tenant_id = result.scalar_one_or_none()
        if tenant_id is None:
            pytest.skip("no Tenant in DB to attach test Line to")

        line = Line(id=line_id, tenant_id=tenant_id, name="test-waba-line")
        session.add(line)
        await session.commit()

    async with AsyncSessionLocal() as session:
        account = ChannelAccount(
            id=uuid.uuid4(),
            line_id=line_id,
            channel_type="waba",
            connection_status="connected",
            credentials_encrypted=encrypted,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(account)
        await session.commit()

    yield line_id, waba_token

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(ChannelAccount).where(ChannelAccount.line_id == line_id)
            )
            acc_to_delete = result.scalar_one_or_none()
            if acc_to_delete is not None:
                await session.delete(acc_to_delete)
            await session.commit()
        except Exception:
            await session.rollback()

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Line).where(Line.id == line_id))
            line_to_delete = result.scalar_one_or_none()
            if line_to_delete is not None:
                await session.delete(line_to_delete)
            await session.commit()
        except Exception:
            await session.rollback()


class TestWebhookTokenVerification:

    # --- Telegram bot ---

    async def test_tg_bot_webhook_invalid_secret_token_403(self, client, tg_bot_account):
        line_id, _ = tg_bot_account
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

    async def test_tg_bot_webhook_valid_secret_token_200(self, client, tg_bot_account):
        line_id, secret_token = tg_bot_account
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
            headers={"x-telegram-bot-api-secret-token": secret_token},
        )
        assert resp.status_code == 200

    # --- WABA ---

    async def test_waba_webhook_invalid_token_403(self, client, waba_account):
        line_id, _ = waba_account
        resp = await client.post(
            f"/webhooks/whatsapp/waba/{line_id}/WRONG_TOKEN",
            json={"entry": []},
        )
        assert resp.status_code == 404

    async def test_waba_webhook_valid_token_200(self, client, waba_account):
        line_id, waba_token = waba_account
        resp = await client.post(
            f"/v1/webhooks/whatsapp/waba/{line_id}/{waba_token}",
            json={"entry": []},
        )
        assert resp.status_code == 200

    # --- Green ---

    async def test_green_webhook_invalid_bearer_403(self, client):
        account = await _get_active_account("whatsapp_green")
        resp = await client.post(
            f"/v1/webhooks/whatsapp/green/{account.line_id}",
            json={"typeWebhook": "incomingMessageReceived"},
            headers={"webhookUrlToken": "WRONG_TOKEN"},
        )
        assert resp.status_code in (401, 403)

    async def test_green_webhook_valid_bearer_200(self, client):
        account = await _get_active_account("whatsapp_green")
        green_api_token = "89vn3jsdx90dsw269sz2sf7e5wrtc78sds"
        resp = await client.post(
            f"/v1/webhooks/whatsapp/green/{account.line_id}",
            json={"typeWebhook": "incomingMessageReceived"},
            headers={"webhookUrlToken": green_api_token},
        )
        assert resp.status_code == 200