import pytest
from httpx import AsyncClient
from app.schemas.line_schemas import ChannelType, SubscriptionPeriod


@pytest.mark.asyncio
async def test_waba_line_lifecycle(client: AsyncClient, token_with_tenant, test_tenant):
    """Test creating WABA line and configuring API key"""
    # 1. Создаем линию
    line_data = {
        "name": "Test WABA Line",
        "channel_type": ChannelType.WABA,
        "subscription_period": SubscriptionPeriod.MONTH,
        "is_demo": True
    }
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/",
        json=line_data,
        headers=token_with_tenant
    )
    print(response.status_code)
    print(response.text)
    assert response.status_code == 201
    line_id = response.json()["id"]

    # 2. Настраиваем API ключ
    waba_data = {"api_key": "test-waba-key-12345"}
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}/account/waba",
        json=waba_data,
        headers=token_with_tenant
    )
    assert response.status_code == 200
    assert response.json()["line_id"] == str(line_id)