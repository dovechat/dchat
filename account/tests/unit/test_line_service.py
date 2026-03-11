import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from fastapi import HTTPException

from app.services.line_service import LineService
from app.schemas.line_schemas import (
    LineCreate,
    LineUpdate,
    LineResponse,
    LineListResponse,
    ChannelType,
    SubscriptionPeriod
)
from models.lines import LineStatus, InstanceStatus


@pytest.fixture
def mock_line():
    """Mock line object with proper __dict__ support"""

    class MockLine:
        def __init__(self):
            self.id = uuid.uuid4()
            self.tenant_id = uuid.uuid4()
            self.name = "Test Line"
            self.channel_type = "whatsapp_green"
            self.status = "active"
            self.is_demo = False
            self.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
            self.connection_state = {"status": "not_connected"}
            self.created_at = datetime.now(timezone.utc)

    return MockLine()


@pytest.fixture
def mock_instance():
    """Mock WhatsApp instance"""
    instance = Mock()
    instance.id = uuid.uuid4()
    instance.provider = "green_api"
    instance.external_id = "wa_instance_12345"
    instance.status = InstanceStatus.idle
    instance.allocated_to_line_id = None
    return instance


@pytest.fixture
def line_service():
    """LineService with mocked repos"""
    mock_line_repo = AsyncMock()
    mock_instance_repo = AsyncMock()
    mock_channel_account_repo = AsyncMock()

    return LineService(
        line_repo=mock_line_repo,
        instance_repo=mock_instance_repo,
        channel_account_repo=mock_channel_account_repo
    )


# === CREATE TESTS ===

@pytest.mark.asyncio
async def test_create_line_whatsapp_with_instance_allocation(line_service, mock_line, mock_instance):
    """Test creating WhatsApp line allocates instance from pool"""
    tenant_id = uuid.uuid4()

    line_data = LineCreate(
        name="My WhatsApp",
        channel_type=ChannelType.WHATSAPP_GREEN,
        subscription_period=SubscriptionPeriod.MONTH
    )

    line_service.line_repo.create_line.return_value = mock_line
    line_service.instance_repo.get_free_instance.return_value = mock_instance
    line_service.instance_repo.allocate_instance.return_value = mock_instance
    line_service.channel_account_repo.create_account.return_value = Mock()

    result = await line_service.create_line(tenant_id, line_data)

    line_service.line_repo.create_line.assert_called_once()
    line_service.instance_repo.get_free_instance.assert_called_once()
    line_service.instance_repo.allocate_instance.assert_called_once()
    line_service.channel_account_repo.create_account.assert_called_once()

    assert isinstance(result, LineResponse)
    assert result.id == mock_line.id


@pytest.mark.asyncio
async def test_create_line_whatsapp_creates_new_instance_if_pool_empty(line_service, mock_line, mock_instance):
    """Test creating new instance when pool is empty"""
    tenant_id = uuid.uuid4()

    line_data = LineCreate(
        name="My WhatsApp",
        channel_type=ChannelType.WHATSAPP_GREEN,
        subscription_period=SubscriptionPeriod.MONTH
    )

    line_service.line_repo.create_line.return_value = mock_line
    line_service.instance_repo.get_free_instance.return_value = None
    line_service.instance_repo.create_instance.return_value = mock_instance
    line_service.instance_repo.allocate_instance.return_value = mock_instance
    line_service.channel_account_repo.create_account.return_value = Mock()

    result = await line_service.create_line(tenant_id, line_data)

    line_service.instance_repo.create_instance.assert_called_once()
    assert isinstance(result, LineResponse)


@pytest.mark.asyncio
async def test_create_demo_line_sets_7_days_expiry(line_service, mock_line):
    """Test demo line expires in 7 days"""
    tenant_id = uuid.uuid4()

    line_data = LineCreate(
        name="Demo Line",
        channel_type=ChannelType.TELEGRAM_BOT,
        is_demo=True
    )

    line_service.line_repo.create_line.return_value = mock_line

    await line_service.create_line(tenant_id, line_data)

    call_args = line_service.line_repo.create_line.call_args[1]
    expires_at = call_args['expires_at']

    expected_expiry = datetime.now(timezone.utc) + timedelta(days=7)
    assert abs((expires_at - expected_expiry).total_seconds()) < 5


# === GET TESTS ===

@pytest.mark.asyncio
async def test_get_lines_returns_list_with_calculated_fields(line_service, mock_line):
    """Test get_lines returns list with days_until_expiry and connection_status"""
    tenant_id = uuid.uuid4()

    line_service.line_repo.get_lines_by_tenant.return_value = [mock_line]

    result = await line_service.get_lines(tenant_id)

    assert len(result) == 1
    assert isinstance(result[0], LineListResponse)
    assert result[0].days_until_expiry is not None
    assert result[0].connection_status == "not_connected"


@pytest.mark.asyncio
async def test_get_line_success(line_service, mock_line):
    """Test getting single line by ID"""
    tenant_id = uuid.uuid4()
    line_id = mock_line.id

    line_service.line_repo.get_line_by_id.return_value = mock_line

    result = await line_service.get_line(line_id, tenant_id)

    line_service.line_repo.get_line_by_id.assert_called_once_with(line_id, tenant_id)
    assert isinstance(result, LineResponse)
    assert result.id == line_id


@pytest.mark.asyncio
async def test_get_line_not_found_raises_404(line_service):
    """Test 404 when line not found"""
    tenant_id = uuid.uuid4()
    line_id = uuid.uuid4()

    line_service.line_repo.get_line_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await line_service.get_line(line_id, tenant_id)

    assert exc.value.status_code == 404


# === UPDATE TESTS ===

@pytest.mark.asyncio
async def test_update_line_success(line_service, mock_line):
    """Test updating line name"""
    tenant_id = uuid.uuid4()
    line_id = mock_line.id

    update_data = LineUpdate(name="New Line Name")

    line_service.line_repo.get_line_by_id.return_value = mock_line
    line_service.line_repo.update_line.return_value = mock_line

    result = await line_service.update_line(line_id, tenant_id, update_data)

    line_service.line_repo.update_line.assert_called_once()
    assert isinstance(result, LineResponse)


@pytest.mark.asyncio
async def test_update_line_not_found_raises_404(line_service):
    """Test 404 when updating non-existent line"""
    tenant_id = uuid.uuid4()
    line_id = uuid.uuid4()

    update_data = LineUpdate(name="New Name")
    line_service.line_repo.get_line_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await line_service.update_line(line_id, tenant_id, update_data)

    assert exc.value.status_code == 404


# === DELETE TESTS ===

@pytest.mark.asyncio
async def test_delete_whatsapp_line_releases_instance(line_service, mock_line, mock_instance):
    """Test deleting WhatsApp line releases instance back to pool"""
    tenant_id = uuid.uuid4()
    line_id = mock_line.id

    line_service.line_repo.get_line_by_id.return_value = mock_line
    line_service.instance_repo.get_instance_by_line.return_value = mock_instance
    line_service.instance_repo.release_instance.return_value = mock_instance

    await line_service.delete_line(line_id, tenant_id)

    line_service.instance_repo.get_instance_by_line.assert_called_once_with(line_id)
    line_service.instance_repo.release_instance.assert_called_once_with(mock_instance)
    line_service.line_repo.delete_line.assert_called_once()


@pytest.mark.asyncio
async def test_delete_line_not_found_raises_404(line_service):
    """Test 404 when deleting non-existent line"""
    tenant_id = uuid.uuid4()
    line_id = uuid.uuid4()

    line_service.line_repo.get_line_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await line_service.delete_line(line_id, tenant_id)

    assert exc.value.status_code == 404


# === PARAMETRIZED TESTS ===

@pytest.mark.parametrize("period,expected_days", [
    (SubscriptionPeriod.MONTH, 30),
    (SubscriptionPeriod.YEAR, 365),
])
@pytest.mark.asyncio
async def test_expiry_calculation_for_periods(line_service, mock_line, period, expected_days):
    """Test expiry dates for different subscription periods"""
    tenant_id = uuid.uuid4()

    line_data = LineCreate(
        name="Test Line",
        channel_type=ChannelType.TELEGRAM_BOT,
        subscription_period=period
    )

    line_service.line_repo.create_line.return_value = mock_line

    await line_service.create_line(tenant_id, line_data)

    call_args = line_service.line_repo.create_line.call_args[1]
    expires_at = call_args['expires_at']

    expected_expiry = datetime.now(timezone.utc) + timedelta(days=expected_days)
    assert abs((expires_at - expected_expiry).total_seconds()) < 5