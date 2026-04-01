# mono/airflow/tests/integration/test_cleanup_service_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from models.lines import Instance, ChannelAccount
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository, InstanceRepository
from services.cleanup_service import CleanupService
from tests.conftest import get_test_db


def make_service(session):
    service = CleanupService(
        conversation_repo=ConversationRepository(session),
        message_repo=MessageRepository(session),
        channel_account_repo=ChannelAccountRepository(session),
        instance_repo=InstanceRepository(session),
    )
    service.s3 = MagicMock()
    return service


def mock_green_api(status_code=200):
    mock_client = AsyncMock()
    mock_client.post.return_value = MagicMock(status_code=status_code)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_client, mock_ctx


# --- инстанс освобождается в БД после очистки ---

@pytest.mark.asyncio
async def test_green_instance_freed_in_db(test_line, test_allocated_instance, test_channel_account):
    mock_client, mock_ctx = mock_green_api()

    with patch("services.cleanup_service.httpx.AsyncClient", return_value=mock_ctx):
        async with get_test_db() as session:
            service = make_service(session)
            await service.cleanup_line(test_line.id, channel_type="whatsapp_green")

    async with get_test_db() as session:
        instance = await session.get(Instance, test_allocated_instance.id)
        assert instance.external_id is None
        assert instance.allocated_to_line_id is None
        assert instance.status.value == "idle"


# --- channel_account удаляется после очистки ---

@pytest.mark.asyncio
async def test_green_channel_account_deleted_in_db(test_line, test_allocated_instance, test_channel_account):
    mock_client, mock_ctx = mock_green_api()

    with patch("services.cleanup_service.httpx.AsyncClient", return_value=mock_ctx):
        async with get_test_db() as session:
            service = make_service(session)
            await service.cleanup_line(test_line.id, channel_type="whatsapp_green")

    async with get_test_db() as session:
        account = await session.get(ChannelAccount, test_channel_account.id)
        assert account is None


# --- идемпотентность: повторная очистка не роняет ошибку ---

@pytest.mark.asyncio
async def test_green_cleanup_idempotent(test_line, test_allocated_instance, test_channel_account):
    mock_client, mock_ctx = mock_green_api()

    with patch("services.cleanup_service.httpx.AsyncClient", return_value=mock_ctx):
        async with get_test_db() as session:
            service = make_service(session)
            await service.cleanup_line(test_line.id, channel_type="whatsapp_green")

    # второй прогон — всё уже удалено, не должно падать
    with patch("services.cleanup_service.httpx.AsyncClient", return_value=mock_ctx):
        async with get_test_db() as session:
            service = make_service(session)
            await service.cleanup_line(test_line.id, channel_type="whatsapp_green")


# --- Green API вернул ошибку — инстанс всё равно освобождается ---

@pytest.mark.asyncio
async def test_green_api_error_still_frees_instance(test_line, test_allocated_instance, test_channel_account):
    mock_client, mock_ctx = mock_green_api(status_code=500)

    with patch("services.cleanup_service.httpx.AsyncClient", return_value=mock_ctx):
        async with get_test_db() as session:
            service = make_service(session)
            await service.cleanup_line(test_line.id, channel_type="whatsapp_green")

    async with get_test_db() as session:
        instance = await session.get(Instance, test_allocated_instance.id)
        assert instance.external_id is None
        assert instance.status.value == "idle"