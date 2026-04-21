"""Unit tests for AdminLineService."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.line_service import AdminLineService
from app.schemas.admin_schemas import SetLineStatusRequest, ExtendLineRequest, LineStatus


def make_uow(*, line=None, lines=None, total=0, channel_expires_at=None):
    uow = MagicMock()
    uow.commit = AsyncMock()

    uow.lines.get_line = AsyncMock(return_value=line)
    uow.lines.get_all_lines = AsyncMock(return_value=lines or [])
    uow.lines.count_lines = AsyncMock(return_value=total)
    uow.lines.set_line_status = AsyncMock(side_effect=lambda l, s: setattr(l, "status", s) or l)
    uow.lines.extend_line = AsyncMock()

    mock_channel = MagicMock()
    mock_channel.expires_at = channel_expires_at
    uow.channels.get_multi = AsyncMock(return_value=[mock_channel] if channel_expires_at else [])
    uow.channels.update = AsyncMock()

    uow.audit.log = AsyncMock()

    return uow


def make_line(**kwargs):
    line = MagicMock()
    line.id = kwargs.get("id", uuid4())
    line.tenant_id = kwargs.get("tenant_id", uuid4())
    line.name = kwargs.get("name", "Test Line")
    line.channel_type = kwargs.get("channel_type", "whatsapp_green")
    line.status = kwargs.get("status", "active")
    line.is_demo = kwargs.get("is_demo", False)
    line.expires_at = kwargs.get(
        "expires_at", datetime.now(timezone.utc) + timedelta(days=30)
    )
    line.created_at = None
    return line


class TestListLines:

    async def test_returns_lines(self):
        lines = [make_line(), make_line()]
        uow = make_uow(lines=lines, total=2)
        service = AdminLineService(uow)

        result = await service.list_lines(
            skip=0, limit=100,
            tenant_id=None, channel_type=None, status=None,
            actor_id=uuid4(),
        )

        assert result.total == 2
        assert len(result.items) == 2

    async def test_passes_filters_to_repo(self):
        tid = uuid4()
        uow = make_uow(lines=[], total=0)
        service = AdminLineService(uow)

        await service.list_lines(
            skip=0, limit=10,
            tenant_id=tid, channel_type="telegram_bot", status="active",
            actor_id=uuid4(),
        )

        uow.lines.get_all_lines.assert_called_once_with(
            skip=0, limit=10,
            tenant_id=tid, channel_type="telegram_bot", status="active",
        )


class TestGetLine:

    async def test_returns_line(self):
        line = make_line()
        uow = make_uow(line=line)
        service = AdminLineService(uow)

        result = await service.get_line(line.id, actor_id=uuid4())

        assert result.id == line.id

    async def test_raises_404_when_not_found(self):
        uow = make_uow(line=None)
        service = AdminLineService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_line(uuid4(), actor_id=uuid4())

        assert exc_info.value.status_code == 404


class TestSetLineStatus:

    async def test_changes_status(self):
        line = make_line(status="active")
        uow = make_uow(line=line)
        service = AdminLineService(uow)

        result = await service.set_line_status(
            line.id,
            SetLineStatusRequest(status=LineStatus.disabled),
            actor_id=uuid4(),
        )

        uow.lines.set_line_status.assert_called_once_with(line, "disabled")
        assert "disabled" in result.message

    async def test_raises_404_when_not_found(self):
        uow = make_uow(line=None)
        service = AdminLineService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_line_status(
                uuid4(),
                SetLineStatusRequest(status=LineStatus.disabled),
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 404

    async def test_audit_contains_old_and_new_status(self):
        line = make_line(status="active")
        uow = make_uow(line=line)
        service = AdminLineService(uow)

        await service.set_line_status(
            line.id,
            SetLineStatusRequest(status=LineStatus.disabled),
            actor_id=uuid4(),
        )

        details = uow.audit.log.call_args.kwargs["details"]
        assert details["old_status"] == "active"
        assert details["new_status"] == "disabled"


class TestExtendLine:

    async def test_extends_from_current_expiry(self):
        future = datetime.now(timezone.utc) + timedelta(days=10)
        line = make_line(expires_at=future)
        uow = make_uow(line=line, channel_expires_at=future)
        service = AdminLineService(uow)

        await service.extend_line(
            line.id,
            ExtendLineRequest(days=30),
            actor_id=uuid4(),
        )

        new_expires = uow.lines.extend_line.call_args.args[1]
        expected = future + timedelta(days=30)
        assert abs((new_expires - expected).total_seconds()) < 5

    async def test_extends_from_now_if_expired(self):
        past = datetime.now(timezone.utc) - timedelta(days=5)
        line = make_line(expires_at=past)
        uow = make_uow(line=line)
        service = AdminLineService(uow)

        await service.extend_line(
            line.id,
            ExtendLineRequest(days=30),
            actor_id=uuid4(),
        )

        new_expires = uow.lines.extend_line.call_args.args[1]
        # Должно быть ~30 дней от сейчас, не от прошлого
        expected_min = datetime.now(timezone.utc) + timedelta(days=29)
        assert new_expires > expected_min

    async def test_raises_404_when_not_found(self):
        uow = make_uow(line=None)
        service = AdminLineService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.extend_line(
                uuid4(),
                ExtendLineRequest(days=30),
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 404

    async def test_audit_contains_days(self):
        line = make_line()
        uow = make_uow(line=line)
        service = AdminLineService(uow)

        await service.extend_line(
            line.id,
            ExtendLineRequest(days=14),
            actor_id=uuid4(),
        )

        details = uow.audit.log.call_args.kwargs["details"]
        assert details["days"] == 14