import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_get_balance(client, test_tenant, token_with_tenant):
    """Test getting balance via API"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/billing/balance",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert "tenant_id" in data
    assert "main_balance" in data
    assert "bonus_balance" in data


@pytest.mark.asyncio
async def test_adjust_balance(client, test_tenant, token_with_tenant):
    """Test manual balance adjustment"""
    from tests.conftest import get_test_db
    from models.billing import BalanceLedger

    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/billing/balance/adjust",
        json={
            "amount": 100.50,
            "balance_type": "main",
            "description": "Manual top-up for testing"
        },
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert Decimal(data["main_balance"]) == Decimal("100.50")

    # Cleanup ledger entries
    async with get_test_db() as session:
        from sqlalchemy import delete
        await session.execute(
            delete(BalanceLedger).where(BalanceLedger.tenant_id == test_tenant.id)
        )
        await session.commit()

    # Reset balance to zero
    from models.billing import Balance
    async with get_test_db() as session:
        balance = await session.get(Balance, test_tenant.id)
        if balance:
            balance.main_balance = Decimal("0.00")
            balance.bonus_balance = Decimal("0.00")
            await session.commit()


@pytest.mark.asyncio
async def test_get_ledger_history(client, test_tenant, token_with_tenant):
    """Test getting ledger history"""
    from tests.conftest import get_test_db
    from models.billing import BalanceLedger

    # First create adjustment to have history
    await client.post(
        f"/api/v1/tenants/{test_tenant.id}/billing/balance/adjust",
        json={
            "amount": 50.00,
            "balance_type": "main",
            "description": "Test entry"
        },
        headers=token_with_tenant
    )

    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/billing/balance/history",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["amount"] == "50.00"

    # Cleanup
    async with get_test_db() as session:
        from sqlalchemy import delete
        await session.execute(
            delete(BalanceLedger).where(BalanceLedger.tenant_id == test_tenant.id)
        )
        await session.commit()

    # Reset balance
    from models.billing import Balance
    async with get_test_db() as session:
        balance = await session.get(Balance, test_tenant.id)
        if balance:
            balance.main_balance = Decimal("0.00")
            await session.commit()


@pytest.mark.asyncio
async def test_get_payments(client, test_tenant, token_with_tenant):
    """Test getting payment history"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/billing/payments",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_payment_status(client, test_tenant, token_with_tenant):
    """Test updating payment status"""
    from tests.conftest import get_test_db
    from models.billing import Payment
    from decimal import Decimal

    # Create test payment
    async with get_test_db() as session:
        payment = Payment(
            tenant_id=test_tenant.id,
            amount=Decimal("100.00"),
            status="pending",
            payment_method="stripe",
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        payment_id = payment.id

    response = await client.patch(
        f"/api/v1/tenants/{test_tenant.id}/billing/payments/{payment_id}",
        json={"status": "paid"},
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paid"

    # Cleanup
    async with get_test_db() as session:
        obj = await session.get(Payment, payment_id)
        if obj:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_get_tariffs(client, token_with_tenant):
    """Test getting tariffs list"""
    response = await client.get(
        "/api/v1/tariffs/",
        headers=token_with_tenant
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_tariff(client, token_with_tenant):
    """Test creating new tariff"""
    from tests.conftest import get_test_db
    from models.billing import Tariff

    response = await client.post(
        "/api/v1/tariffs/",
        json={
            "name": "Test Telegram Bot Tariff",
            "channel_type": "telegram_bot",
            "period": 30,
            "price": 10.00,
            "is_active": True
        },
        headers=token_with_tenant
    )

    assert response.status_code == 201
    data = response.json()

    assert data["channel_type"] == "telegram_bot"
    assert data["period_days"] == 30
    assert Decimal(data["price"]) == Decimal("10.00")

    tariff_id = data["id"]

    # Cleanup
    async with get_test_db() as session:
        obj = await session.get(Tariff, tariff_id)
        if obj:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_update_tariff(client, token_with_tenant):
    """Test updating tariff"""
    from tests.conftest import get_test_db
    from models.billing import Tariff
    from decimal import Decimal

    # Create test tariff
    async with get_test_db() as session:
        tariff = Tariff(
            name="Test VK Yearly",
            channel_type="vk",
            period_days=365,
            price=Decimal("100.00"),
            is_active=True
        )
        session.add(tariff)
        await session.commit()
        await session.refresh(tariff)
        tariff_id = tariff.id

    response = await client.patch(
        f"/api/v1/tariffs/{tariff_id}",
        json={"price": 120.00, "is_active": False},
        headers=token_with_tenant
    )

    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["price"]) == Decimal("120.00")
    assert data["is_active"] is False

    # Cleanup
    async with get_test_db() as session:
        obj = await session.get(Tariff, tariff_id)
        if obj:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_unauthorized_access(client, test_tenant):
    """Test that endpoints require authentication"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/billing/balance"
    )

    assert response.status_code == 403