"""Unit tests for AdminBillingService."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.billing_service import AdminBillingService
from app.schemas.admin_schemas import AdjustmentRequest


def make_uow(*, entries=None, balance=None):
    uow = MagicMock()
    uow.commit = AsyncMock()

    uow.billing.get_ledger = AsyncMock(return_value=entries or [])
    uow.billing.get_tenant_balance = AsyncMock(
        return_value=balance or {"main": 0.0, "bonus": 0.0}
    )
    uow.billing.create_adjustment = AsyncMock(return_value=MagicMock())

    uow.audit.log = AsyncMock()

    return uow


def make_entry(**kwargs):
    entry = MagicMock()
    entry.id = kwargs.get("id", 1)
    entry.tenant_id = kwargs.get("tenant_id", uuid4())
    entry.amount = kwargs.get("amount", Decimal("100.00"))
    entry.balance_type = kwargs.get("balance_type", "main")
    entry.operation_type = kwargs.get("operation_type", "deposit")
    entry.description = kwargs.get("description", "Test")
    entry.reference_id = None
    entry.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    return entry


class TestGetLedger:

    async def test_returns_entries(self):
        entries = [make_entry(), make_entry()]
        uow = make_uow(entries=entries)
        service = AdminBillingService(uow)

        result = await service.get_ledger(
            skip=0, limit=100,
            tenant_id=None, operation_type=None, balance_type=None,
            actor_id=uuid4(),
        )

        assert result.total == 2
        assert len(result.items) == 2

    async def test_raises_400_for_invalid_operation_type(self):
        uow = make_uow()
        service = AdminBillingService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_ledger(
                skip=0, limit=100,
                tenant_id=None, operation_type="nonexistent", balance_type=None,
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 400

    async def test_valid_operation_types_pass(self):
        uow = make_uow(entries=[])
        service = AdminBillingService(uow)

        for op_type in ["deposit", "charge", "adjustment", "bonus_grant", "refund"]:
            result = await service.get_ledger(
                skip=0, limit=10,
                tenant_id=None, operation_type=op_type, balance_type=None,
                actor_id=uuid4(),
            )
            assert result.total == 0


class TestGetBalance:

    async def test_returns_main_and_bonus(self):
        uow = make_uow(balance={"main": 500.0, "bonus": 50.0})
        service = AdminBillingService(uow)

        result = await service.get_balance(uuid4(), actor_id=uuid4())

        assert result.main == 500.0
        assert result.bonus == 50.0

    async def test_zero_balance(self):
        uow = make_uow(balance={"main": 0.0, "bonus": 0.0})
        service = AdminBillingService(uow)

        result = await service.get_balance(uuid4(), actor_id=uuid4())

        assert result.main == 0.0
        assert result.bonus == 0.0


class TestCreateAdjustment:

    async def test_creates_adjustment(self):
        uow = make_uow()
        service = AdminBillingService(uow)
        tenant_id = uuid4()
        actor_id = uuid4()

        result = await service.create_adjustment(
            tenant_id=tenant_id,
            request=AdjustmentRequest(
                amount=Decimal("200.00"),
                balance_type="main",
                description="Manual top-up",
            ),
            actor_id=actor_id,
        )

        uow.billing.create_adjustment.assert_called_once_with(
            tenant_id=tenant_id,
            amount=200.0,
            balance_type="main",
            description="Manual top-up",
            admin_user_id=actor_id,
        )
        assert "200" in result.message

    async def test_negative_adjustment(self):
        """Отрицательный amount — списание, должно пройти без ошибок."""
        uow = make_uow()
        service = AdminBillingService(uow)

        result = await service.create_adjustment(
            tenant_id=uuid4(),
            request=AdjustmentRequest(
                amount=Decimal("-50.00"),
                balance_type="bonus",
                description="Correction",
            ),
            actor_id=uuid4(),
        )

        assert result.message is not None

    async def test_audit_logged_with_details(self):
        uow = make_uow()
        service = AdminBillingService(uow)

        await service.create_adjustment(
            tenant_id=uuid4(),
            request=AdjustmentRequest(
                amount=Decimal("100.00"),
                balance_type="main",
                description="Test adjustment",
            ),
            actor_id=uuid4(),
        )

        call_kwargs = uow.audit.log.call_args.kwargs
        assert call_kwargs["action"] == "balance_adjustment"
        assert call_kwargs["details"]["description"] == "Test adjustment"
        assert call_kwargs["details"]["balance_type"] == "main"