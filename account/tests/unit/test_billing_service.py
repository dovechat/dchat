import pytest
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from fastapi import HTTPException

from app.services.billing_service import BillingService
from app.schemas.billing_schemas import (
    BalanceResponse,
    BalanceAdjust,
    BalanceLedgerResponse,
    BillingHistoryItem,
    PaymentResponse,
    PaymentStatusUpdate,
    TariffCreate,
    TariffUpdate,
    TariffResponse
)


@pytest.fixture
def mock_balance():
    """Mock balance object"""

    class MockBalance:
        def __init__(self):
            self.tenant_id = uuid.uuid4()
            self.main_balance = Decimal("100.00")
            self.bonus_balance = Decimal("50.00")
            self.updated_at = None

    return MockBalance()


@pytest.fixture
def mock_ledger():
    """Mock ledger entry"""

    class MockLedger:
        def __init__(self):
            self.id = 1
            self.tenant_id = uuid.uuid4()
            self.amount = Decimal("100.00")
            self.balance_type = "main"
            self.description = "Test adjustment"
            self.reference_id = None
            self.created_at = None

    return MockLedger()


@pytest.fixture
def mock_payment():
    """Mock payment object"""

    class MockPayment:
        def __init__(self):
            self.id = uuid.uuid4()
            self.tenant_id = uuid.uuid4()
            self.amount = Decimal("500.00")
            self.status = "pending"
            self.payment_method = "stripe"
            self.external_id = "pi_123"
            self.created_at = None
            self.updated_at = None

    return MockPayment()


@pytest.fixture
def mock_tariff():
    """Mock tariff object"""

    class MockTariff:
        def __init__(self):
            self.id = uuid.uuid4()
            self.name = "test tariff"
            self.channel_type = "telegram_bot"
            self.period_days = 1
            self.price = Decimal("10.00")
            self.is_active = True
            self.created_at = None
            self.updated_at = None

    return MockTariff()


@pytest.fixture
def billing_service():
    """BillingService with mocked repos"""
    mock_balance_repo = AsyncMock()
    mock_ledger_repo = AsyncMock()
    mock_payment_repo = AsyncMock()
    mock_tariff_repo = AsyncMock()

    return BillingService(
        balance_repo=mock_balance_repo,
        ledger_repo=mock_ledger_repo,
        payment_repo=mock_payment_repo,
        tariff_repo=mock_tariff_repo
    )


# === BALANCE TESTS ===

@pytest.mark.asyncio
async def test_get_balance_success(billing_service, mock_balance):
    """Test getting balance"""
    tenant_id = mock_balance.tenant_id

    billing_service.balance_repo.get_by_tenant.return_value = mock_balance

    result = await billing_service.get_balance(tenant_id)

    assert isinstance(result, BalanceResponse)
    assert result.main_balance == Decimal("100.00")
    assert result.bonus_balance == Decimal("50.00")


@pytest.mark.asyncio
async def test_get_balance_creates_if_not_exists(billing_service, mock_balance):
    """Test balance creation if doesn't exist"""
    tenant_id = mock_balance.tenant_id

    billing_service.balance_repo.get_by_tenant.return_value = None
    billing_service.balance_repo.create_balance.return_value = mock_balance

    result = await billing_service.get_balance(tenant_id)

    billing_service.balance_repo.create_balance.assert_called_once_with(tenant_id)
    assert isinstance(result, BalanceResponse)


@pytest.mark.asyncio
async def test_adjust_balance_success(billing_service, mock_balance, mock_ledger):
    """Test manual balance adjustment"""
    tenant_id = mock_balance.tenant_id

    adjustment = BalanceAdjust(
        amount=Decimal("200.00"),
        balance_type="main",
        description="Manual top-up"
    )

    billing_service.balance_repo.get_by_tenant.return_value = mock_balance
    billing_service.balance_repo.adjust_balance.return_value = mock_balance
    billing_service.ledger_repo.create_entry.return_value = mock_ledger

    result = await billing_service.adjust_balance(tenant_id, adjustment)

    billing_service.balance_repo.adjust_balance.assert_called_once()
    billing_service.ledger_repo.create_entry.assert_called_once()
    assert isinstance(result, BalanceResponse)


@pytest.mark.asyncio
async def test_get_ledger_history(billing_service, mock_ledger):
    """Test getting ledger history"""
    tenant_id = uuid.uuid4()

    billing_service.ledger_repo.get_history.return_value = [mock_ledger]

    result = await billing_service.get_ledger_history(tenant_id)

    assert len(result) == 1
    assert isinstance(result[0], BalanceLedgerResponse)


# === PAYMENT TESTS ===

@pytest.mark.asyncio
async def test_get_payments(billing_service, mock_payment):
    """Test getting payment history"""
    tenant_id = mock_payment.tenant_id

    billing_service.payment_repo.get_payments_by_tenant.return_value = [mock_payment]

    result = await billing_service.get_payments(tenant_id)

    assert len(result) == 1
    assert isinstance(result[0], BillingHistoryItem)
    assert result[0].status == "pending"


@pytest.mark.asyncio
async def test_update_payment_status_success(billing_service, mock_payment):
    """Test updating payment status"""
    payment_id = mock_payment.id
    tenant_id = mock_payment.tenant_id

    status_update = PaymentStatusUpdate(status="paid")

    billing_service.payment_repo.get_by_id.return_value = mock_payment
    mock_payment.status = "paid"
    billing_service.payment_repo.update_status.return_value = mock_payment

    result = await billing_service.update_payment_status(payment_id, tenant_id, status_update)

    billing_service.payment_repo.update_status.assert_called_once_with(mock_payment, "paid")
    assert result.status == "paid"


@pytest.mark.asyncio
async def test_update_payment_status_not_found(billing_service):
    """Test 404 when payment not found"""
    payment_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    status_update = PaymentStatusUpdate(status="paid")

    billing_service.payment_repo.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await billing_service.update_payment_status(payment_id, tenant_id, status_update)

    assert exc.value.status_code == 404


# === TARIFF TESTS ===

@pytest.mark.asyncio
async def test_get_tariffs(billing_service, mock_tariff):
    """Test getting all active tariffs"""
    billing_service.tariff_repo.get_all_active.return_value = [mock_tariff]

    result = await billing_service.get_tariffs()

    assert len(result) == 1
    assert isinstance(result[0], TariffResponse)
    assert result[0].channel_type == "telegram_bot"


@pytest.mark.asyncio
async def test_create_tariff_success(billing_service, mock_tariff):
    """Test creating new tariff"""
    tariff_data = TariffCreate(
        name="test tariff",
        channel_type="telegram_bot",
        period=1,
        price=Decimal("10.00"),
        is_active=True
    )

    billing_service.tariff_repo.create_tariff.return_value = mock_tariff

    result = await billing_service.create_tariff(tariff_data)

    billing_service.tariff_repo.create_tariff.assert_called_once()
    assert isinstance(result, TariffResponse)


@pytest.mark.asyncio
async def test_update_tariff_success(billing_service, mock_tariff):
    """Test updating tariff"""
    tariff_id = mock_tariff.id

    tariff_update = TariffUpdate(price=Decimal("15.00"))

    billing_service.tariff_repo.get_by_id.return_value = mock_tariff
    mock_tariff.price = Decimal("15.00")
    billing_service.tariff_repo.update_tariff.return_value = mock_tariff

    print(f"************** result BEFORE tariff_id {tariff_id} tariff_update {tariff_update}")
    result = await billing_service.update_tariff(tariff_id, tariff_update)
    print(f"************** result {result}")

    billing_service.tariff_repo.update_tariff.assert_called_once()
    assert result.price == Decimal("15.00")


@pytest.mark.asyncio
async def test_update_tariff_not_found(billing_service):
    """Test 404 when tariff not found"""
    tariff_id = uuid.uuid4()

    tariff_update = TariffUpdate(price=Decimal("15.00"))

    billing_service.tariff_repo.get_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await billing_service.update_tariff(tariff_id, tariff_update)

    assert exc.value.status_code == 404