import pytest
from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_create_line_whatsapp(client, test_tenant, token_with_tenant):
    """Test creating WhatsApp line via API"""
    print(f"------- test_tenant {test_tenant.id}")
    print(f"------- token_with_tenant {token_with_tenant}")
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/",
        json={
            "name": "My WhatsApp Line",
            # "channel_type": "whatsapp_green",
            # "subscription_period": "month",
            # "is_demo": False
        },
        headers=token_with_tenant
    )

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "My WhatsApp Line"
    # assert data["channel_type"] == "whatsapp_green"
    # assert data["tenant_id"] == str(test_tenant.id)
    assert data["status"] == "active"
    assert "id" in data
    # assert "expires_at" in data


'''
@pytest.mark.asyncio
async def test_create_demo_line(client, test_tenant, token_with_tenant):
    """Test creating demo line with 7 days expiry"""
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/",
        json={
            "name": "Demo Line",
            # "channel_type": "telegram_bot",
            "is_demo": True
        },
        headers=token_with_tenant
    )

    assert response.status_code == 201
    data = response.json()

    print("data", data)

    assert data["is_demo"] is True

    # expires_at = datetime.fromisoformat(
    #    data["expires_at"].replace("Z", "+00:00")
    # ).astimezone(timezone.utc)
    # expected_expiry = datetime.now(timezone.utc) + timedelta(days=7)

   #  assert abs((expires_at - expected_expiry).total_seconds()) < 60
'''

@pytest.mark.asyncio
async def test_list_lines(client, test_tenant, test_line, token_with_tenant):
    """Test listing all lines for tenant"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1

    line_data = data[0]
    assert "id" in line_data
    assert "name" in line_data
    # assert "channel_type" in line_data
    assert "days_until_expiry" in line_data
    assert "connection_status" in line_data


@pytest.mark.asyncio
async def test_get_line_by_id(client, test_tenant, test_line, token_with_tenant):
    """Test getting single line by ID"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(test_line.id)
    assert data["name"] == test_line.name
    # assert data["channel_type"] == test_line.channel_type


@pytest.mark.asyncio
async def test_get_line_not_found(client, test_tenant, token_with_tenant):
    """Test 404 when line doesn't exist"""
    import uuid
    fake_id = uuid.uuid4()

    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/{fake_id}",
        headers=token_with_tenant
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_line_name(client, test_tenant, test_line, token_with_tenant):
    """Test updating line name"""
    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}",
        json={"name": "Updated Line Name"},
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert data["name"] == "Updated Line Name"
    assert data["id"] == str(test_line.id)


@pytest.mark.asyncio
async def test_update_line_status(client, test_tenant, test_line, token_with_tenant):
    """Test updating line status"""
    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}",
        json={"status": "disabled"},
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "disabled"


@pytest.mark.asyncio
async def test_delete_line(client, test_tenant, test_line, token_with_tenant):
    """Test deleting line"""
    response = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}",
        headers=token_with_tenant
    )

    assert response.status_code == 204

    get_response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/{test_line.id}",
        headers=token_with_tenant
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_line_releases_instance(client, test_tenant, test_allocated_instance, token_with_tenant):
    """Test that deleting WhatsApp line releases instance back to pool"""
    from tests.conftest import get_test_db
    from models.lines import Instance, Line

    async with get_test_db() as session:
        line = await session.get(Line, test_allocated_instance.allocated_to_line_id)
        line_id = line.id

    print("line", line)

    response = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/lines/{line_id}",
        headers=token_with_tenant
    )

    print("response", response)

    assert response.status_code == 204

    async with get_test_db() as session:
        instance = await session.get(Instance, test_allocated_instance.id)
        assert instance.allocated_to_line_id is None
        assert instance.status.value == "idle"


@pytest.mark.asyncio
async def test_unauthorized_access(client, test_tenant, test_line):
    """Test that endpoints require authentication"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/lines/"
    )

    assert response.status_code == 403

'''
@pytest.mark.parametrize("channel_type", [
    "whatsapp_green",
    "waba",
    "telegram_user",
    "telegram_bot",
    "vk"
])
@pytest.mark.asyncio
async def test_create_line_all_channel_types(client, test_tenant, token_with_tenant, channel_type):
    """Test creating lines for all supported channel types"""
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/lines/",
        json={
            "name": f"Test {channel_type}",
            "channel_type": channel_type,
            "subscription_period": "month"
        },
        headers=token_with_tenant
    )

    assert response.status_code == 201
    data = response.json()
    assert data["channel_type"] == channel_type
'''