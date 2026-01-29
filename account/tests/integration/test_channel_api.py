import pytest
import uuid


@pytest.mark.asyncio
async def test_get_channel_account(client, test_tenant, test_line, token_with_tenant):
    """Test getting channel account via API"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}/account/",
        headers=token_with_tenant
    )

    # !!! Account might not exist yet, expect 404 or 200
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_update_telegram_bot_credentials(client, test_tenant, token_with_tenant):
    """Test updating Telegram Bot credentials"""
    from tests.conftest import get_test_db
    from models.lines import Line
    from app.schemas.line_schemas import ChannelType

    # Create telegram_bot line
    async with get_test_db() as session:
        from datetime import datetime, timedelta, timezone
        line = Line(
            tenant_id=test_tenant.id,
            name="Test Telegram Bot",
            channel_type=ChannelType.TELEGRAM_BOT.value,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            connection_state={"status": "not_connected"}
        )
        session.add(line)
        await session.commit()
        await session.refresh(line)
        line_id = line.id

    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/telegram-bot",
        json={
            "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "webhook_url": "https://example.com/webhook"
        },
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert data["line_id"] == str(line_id)
    assert data["channel_type"] == "telegram_bot"

    # Cleanup
    async with get_test_db() as session:
        obj = await session.get(Line, line_id)
        if obj:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_update_wrong_channel_type(client, test_tenant, test_line, token_with_tenant):
    """Test 400 when trying to update with wrong channel type"""
    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}/account/vk",
        json={
            "access_token": "vk_token",
            "group_id": "12345"
        },
        headers=token_with_tenant
    )

    # test_line is whatsapp_qr, so VK update should fail
    assert response.status_code == 400

'''
@pytest.mark.asyncio
async def test_update_state(client, test_tenant, test_line, token_with_tenant):
    """Test updating channel state"""
    # First create account
    from tests.conftest import get_test_db
    from models.lines import ChannelAccount

    async with get_test_db() as session:
        account = ChannelAccount(
            line_id=test_line.id,
            credentials_encrypted={"test": "data"},
            state_json={"status": "initial"}
        )
        session.add(account)
        await session.commit()

    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}/account/state",
        json={
            "state_json": {"status": "connected", "webhook_active": True}
        },
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert data["state_json"]["status"] == "connected"
    assert data["state_json"]["webhook_active"] is True
'''

@pytest.mark.asyncio
async def test_unauthorized_access(client, test_tenant, test_line):
    """Test that endpoints require authentication"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}/account/"
    )

    assert response.status_code == 403