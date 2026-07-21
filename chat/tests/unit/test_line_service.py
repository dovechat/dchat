import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.line_service import LineService


def make_service():
    db = MagicMock()
    service = LineService(db)
    service.permission_repo = AsyncMock()
    service.line_repo = AsyncMock()
    service.channel_repo = AsyncMock()
    return service


# ---------- get_user_lines ----------

@pytest.mark.asyncio
async def test_get_user_lines_owner_returns_all_tenant_lines():
    service = make_service()
    tenant_id = uuid.uuid4()
    lines = [MagicMock(), MagicMock()]
    service.line_repo.get_multi = AsyncMock(return_value=lines)

    result = await service.get_user_lines(uuid.uuid4(), "owner", tenant_id)

    assert result == lines
    service.line_repo.get_multi.assert_awaited_once_with(filters={"tenant_id": tenant_id})
    service.permission_repo.get_user_line_ids.assert_not_called()


@pytest.mark.asyncio
async def test_get_user_lines_member_no_permissions_returns_empty():
    service = make_service()
    service.permission_repo.get_user_line_ids = AsyncMock(return_value=[])

    result = await service.get_user_lines(uuid.uuid4(), "member", uuid.uuid4())

    assert result == []
    service.line_repo.get_multi.assert_not_called()


@pytest.mark.asyncio
async def test_get_user_lines_member_with_permissions():
    service = make_service()
    line_ids = [uuid.uuid4(), uuid.uuid4()]
    lines = [MagicMock(), MagicMock()]
    service.permission_repo.get_user_line_ids = AsyncMock(return_value=line_ids)
    service.line_repo.get_multi = AsyncMock(return_value=lines)

    result = await service.get_user_lines(uuid.uuid4(), "member", uuid.uuid4())

    assert result == lines
    service.line_repo.get_multi.assert_awaited_once_with(filters={"id": line_ids})


# ---------- get_line_channels ----------

@pytest.mark.asyncio
async def test_get_line_channels_returns_channels():
    service = make_service()
    line_id = uuid.uuid4()
    channels = [MagicMock(), MagicMock()]
    service.channel_repo.get_multi = AsyncMock(return_value=channels)

    result = await service.get_line_channels(line_id)

    assert result == channels
    service.channel_repo.get_multi.assert_awaited_once_with(filters={"line_id": line_id})


@pytest.mark.asyncio
async def test_get_line_channels_empty():
    service = make_service()
    service.channel_repo.get_multi = AsyncMock(return_value=[])

    result = await service.get_line_channels(uuid.uuid4())

    assert result == []