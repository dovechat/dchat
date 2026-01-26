import uuid
import pytest
from httpx import AsyncClient
from fastapi import status
from core.config import settings


async def test_create_tenant(client, token_headers):
    # This data must match the schema you use in Swagger
    valid_tenant_data = {
        "name": "New Tenant",
        "description": "Test Description"
    }
    response = await client.post(
        "/api/v1/tenant/create",
        json=valid_tenant_data,
        headers=token_headers
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_get_tenant_api(client: AsyncClient, token_headers: dict, test_tenant):
    response = await client.get(
        f"/api/v1/tenant/{test_tenant.id}",
        headers=token_headers
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_get_all_tenants_api(client, test_tenant, token_headers):
    response = await client.get(
        "/api/v1/tenant/",
        headers=token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(item["id"] == str(test_tenant.id) for item in data)


@pytest.mark.asyncio
async def test_update_tenant_api(client: AsyncClient, token_headers: dict, test_tenant):
    payload = {"name": "Patched Name"}
    response = await client.patch(
        f"/api/v1/tenant/{test_tenant.id}",
        json=payload,
        headers=token_headers
    )
    assert response.status_code == status.HTTP_200_OK

@pytest.mark.asyncio
async def test_delete_tenant_api(client: AsyncClient, token_headers: dict, test_tenant):
    response = await client.delete(
        f"/api/v1/tenant/{test_tenant.id}",
        headers=token_headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_update_bank_details_ru(client: AsyncClient, token_headers: dict, test_tenant):
    tenant_id = test_tenant.id
    payload = {
        "bank_name": "T-Bank",
        "account_number": "40817810000000000000",
        "bic": "044525974",
        "corr_account": "30101810145250000974",
        "kpp": "771001001",
        "currency": "RUB",
        "is_primary": True
    }

    # Create/Update
    response = await client.patch(
        f"/api/v1/tenant/{tenant_id}/banking/ru",
        json=payload,
        headers=token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["bank_name"] == payload["bank_name"]
    assert data["tenant_id"] == str(tenant_id)

    # Update existing
    payload["bank_name"] = "Sberbank"
    update_res = await client.patch(
        f"/api/v1/tenant/{tenant_id}/banking/ru",
        json=payload,
        headers=token_headers,
    )

    assert update_res.status_code == 200
    assert update_res.json()["bank_name"] == "Sberbank"



''''
@pytest.mark.asyncio
async def test_get_tenant_api_forbidden(client: AsyncClient, token_headers: dict):
    # Generating a random UUID that definitely doesn't belong to this user
    random_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/tenant/{random_id}",
        headers=token_headers
    )
    # Now it must return 404 because of user_id filtering
    assert response.status_code == status.HTTP_404_NOT_FOUND
'''