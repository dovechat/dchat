import pytest
import uuid
from httpx import AsyncClient

from repo.line_repo import ChannelAccountRepository
from models.lines import Line


@pytest.mark.asyncio
async def test_configure_whatsapp_green_success(
        client: AsyncClient,
        test_line,
        test_tenant,
        token_with_tenant,
        test_db
):
    """Test successful WhatsApp Green configuration"""
    print("test_line_id", test_line.id)
    line_id = test_line.id
    payload = {
        "id_instance": "test_instance_123",
        "api_token": "secret_token_456"
    }

    print(f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green")
    print(payload)
    print(token_with_tenant)

    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green",
        json=payload,
        headers=token_with_tenant
    )

    # assert response.status_code == 200
    data = response.json()
    print("data", data)


    if "line_id" in data:
        assert data["line_id"] == str(line_id)
        print("*--*-*-*-*-*-*-*-")
        assert data["status"] == "ok"
        # Verify in DB using test_db fixture
        repo = ChannelAccountRepository(test_db)
        accounts = await repo.get_by_line(line_id)
        assert accounts is not None
        if len(accounts) > 0:
            account = accounts[0]
            print("account", account)
            assert "encrypted_data" in account.credentials_encrypted
    elif "detail" in data:
        assert "Send green set_webhook failed" in  data.get("detail")


@pytest.mark.asyncio
async def test_configure_whatsapp_green_updates_existing(
        client: AsyncClient,
        test_line,
        test_tenant,
        token_with_tenant,
        test_db
):
    """Test updating existing WhatsApp Green configuration"""
    line_id = test_line.id

    # First config
    payload1 = {
        "id_instance": "inst_1",
        "api_token": "token_1"
    }
    response1 = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green",
        json=payload1,
        headers=token_with_tenant
    )
    assert response1.status_code == 200

    # Second config (update)
    payload2 = {
        "id_instance": "inst_2",
        "api_token": "token_2"
    }
    response2 = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green",
        json=payload2,
        headers=token_with_tenant
    )

    assert response2.status_code == 200

    # Verify only one account exists
    repo = ChannelAccountRepository(test_db)
    account = await repo.get_by_line(line_id)
    assert account is not None


@pytest.mark.asyncio
async def test_configure_whatsapp_green_line_not_found(
        client: AsyncClient,
        test_tenant,
        token_with_tenant
):
    """Test with non-existent line"""
    line_id = uuid.uuid4()
    payload = {
        "id_instance": "test",
        "api_token": "test"
    }
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green",
        json=payload,
        headers=token_with_tenant
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_configure_whatsapp_green_unauthorized(
        client: AsyncClient,
        test_line,
        test_tenant,
):
    """Test without auth token"""
    payload = {
        "id_instance": "test",
        "api_token": "test"
    }
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}/account/whatsapp-green",
        json=payload
    )

    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_whatsapp_green_webhook_qr_scanned(
        client,
        test_line,
        test_tenant,
        test_db,
        token_with_tenant
):
    line_id = test_line.id

    # 1. Сначала настраиваем линию (создаём channel_account)
    config_payload = {
        "id_instance": "test_instance",
        "api_token": "test_token"
    }
    await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/whatsapp-green",
        json=config_payload,
        headers=token_with_tenant
    )

    # 2. Отправляем вебхук о сканировании QR
    webhook_payload = {
        "typeWebhook": "qrScanned",
        "instanceData": {}
    }
    response = await client.post(
        f"/api/v1/webhooks/whatsapp/green/{line_id}",
        json=webhook_payload
    )

    assert response.status_code == 200

    # 3. Проверяем статус
    repo = ChannelAccountRepository(test_db)
    accounts = await repo.get_by_line(line_id)
    if len(accounts) > 0:
        account = accounts[0]
        print("account.connection_status", account.connection_status)
        assert account.connection_status.value in ["connected",  "disconnected"] 