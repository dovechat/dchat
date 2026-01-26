import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status
from app.services.tenant_services import RequisitsService, TenantService
from app.schemas.tenant_schemas import BankDetailsRead, TenantResponse


@pytest.fixture
def mock_tenant():
    """Helper to create a mock tenant object"""
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.user_id = uuid.uuid4()
    tenant.name = "Test Tenant"
    tenant.locale = "en"
    tenant.payment = "wire"
    tenant.status = "active"
    tenant.banking_details = None
    return tenant


@pytest.mark.asyncio
async def test_get_all_tenants_service(mock_tenant):
    mock_repo = AsyncMock()
    service = TenantService(repo=mock_repo)
    mock_repo.get_all_tenants.return_value = [mock_tenant]

    result = await service.get_all_tenants(user_id=mock_tenant.user_id)

    mock_repo.get_all_tenants.assert_called_once_with(user_id=mock_tenant.user_id)
    assert len(result) == 1
    assert isinstance(result[0], TenantResponse)


@pytest.mark.asyncio
async def test_get_tenant_success(mock_tenant):
    mock_repo = AsyncMock()
    service = TenantService(repo=mock_repo)
    mock_repo.get_tenant_by_id.return_value = mock_tenant

    result = await service.get_tenant(mock_tenant.id, mock_tenant.user_id)

    mock_repo.get_tenant_by_id.assert_called_once_with(mock_tenant.id, user_id=mock_tenant.user_id)
    assert result.id == mock_tenant.id


@pytest.mark.asyncio
async def test_update_tenant_success(mock_tenant):
    mock_repo = AsyncMock()
    service = TenantService(repo=mock_repo)
    update_data = {"name": "New Name"}
    mock_repo.update_tenant.return_value = mock_tenant

    await service.update_tenant(mock_tenant.id, update_data, mock_tenant.user_id)

    # Match the actual call structure: (tenant_id, user_id, data) as keywords
    mock_repo.update_tenant.assert_called_once_with(
        tenant_id=mock_tenant.id, 
        user_id=mock_tenant.user_id, 
        data=update_data
    )

@pytest.mark.asyncio
async def test_delete_tenant_api(client, test_tenant, token_headers):
    # Delete the tenant
    response = await client.delete(
        f"/api/v1/tenant/{test_tenant.id}", 
        headers=token_headers
    )
    assert response.status_code == 204

    # Verify it is gone
    get_response = await client.get(
        f"/api/v1/tenant/{test_tenant.id}", 
        headers=token_headers
    )
    assert get_response.status_code == 404


@pytest.mark.parametrize("method_name, args", [
    ("get_tenant", (uuid.uuid4(), uuid.uuid4())),
    ("update_tenant", (uuid.uuid4(), {}, uuid.uuid4())),
    ("delete_tenant", (uuid.uuid4(), uuid.uuid4())),
])
@pytest.mark.asyncio
async def test_tenant_methods_404(method_name, args):
    mock_repo = AsyncMock()
    service = TenantService(repo=mock_repo)
    mock_repo.get_tenant_by_id.return_value = None
    mock_repo.update_tenant.return_value = None
    mock_repo.delete_tenant.return_value = False

    with pytest.raises(HTTPException) as exc:
        await getattr(service, method_name)(*args)
    assert exc.value.status_code == 404


# --- bank requisites

@pytest.mark.asyncio
async def test_update_tenant_success(mock_tenant):
    """
    Testing successful banking details update with all required fields.
    """
    mock_repo = AsyncMock()
    service = RequisitsService(repo=mock_repo)

    update_data = MagicMock()

    # Adding all fields required by BankDetailsRead schema
    repo_output = {
        "id": uuid.uuid4(),
        "tenant_id": mock_tenant.id,
        "bank_name": "T-Bank",
        "bic": "044525974",
        "account_number": "40817810000000000000",
        "currency": "RUB",
        "is_primary": True
    }
    mock_repo.update_bank_details.return_value = repo_output

    # Act
    result = await service.update_tenant_banking(
        tenant_id=mock_tenant.id,
        data=update_data,
        user_id=mock_tenant.user_id
    )

    # Assert
    assert isinstance(result, BankDetailsRead)
    assert result.id == repo_output["id"]
    mock_repo.update_bank_details.assert_called_once_with(
        tenant_id=mock_tenant.id,
        data=update_data,
        user_id=mock_tenant.user_id
    )


@pytest.mark.asyncio
async def test_update_tenant_banking_not_found(mock_tenant):
    """
    Test 404 response when repository returns None.
    Check only status code to avoid fragile tests.
    """
    mock_repo = AsyncMock()
    service = RequisitsService(repo=mock_repo)

    mock_repo.update_bank_details.return_value = None
    update_data = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await service.update_tenant_banking(
            tenant_id=mock_tenant.id,
            data=update_data,
            user_id=mock_tenant.user_id
        )

    assert exc.value.status_code == 404