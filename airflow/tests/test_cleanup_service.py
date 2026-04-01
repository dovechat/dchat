# mono/airflow/tests/test_cleanup_service.py
import uuid
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.cleanup_service import CleanupService


@pytest.fixture
def line_id():
    return uuid.uuid4()


@pytest.fixture
def make_service():
    def _make(instance=None, channel_account=None, conversations=None):
        conversation_repo = AsyncMock()
        message_repo = AsyncMock()
        channel_account_repo = AsyncMock()
        instance_repo = AsyncMock()

        conversation_repo.get_by_line.return_value = conversations or []
        channel_account_repo.get_by_line.return_value = channel_account
        instance_repo.get_by_line.return_value = instance

        service = CleanupService(
            conversation_repo=conversation_repo,
            message_repo=message_repo,
            channel_account_repo=channel_account_repo,
            instance_repo=instance_repo,
        )
        service.s3 = MagicMock()
        return service, conversation_repo, message_repo, channel_account_repo, instance_repo

    return _make


@pytest.fixture
def green_instance(line_id):
    instance = MagicMock()
    instance.id = uuid.uuid4()
    instance.external_id = "1101234567"
    instance.allocated_to_line_id = line_id
    return instance


@pytest.fixture
def channel_account():
    acc = MagicMock()
    acc.credentials_encrypted = {"encrypted_data": "encrypted-token"}
    return acc


DECRYPTED_GREEN_CREDS = json.dumps({"id_instance": "1101234567", "api_token": "test-token"})


# --- whatsapp_green: успешный logout и clearMessagesQueue ---

@pytest.mark.asyncio
async def test_green_cleanup_calls_api(line_id, make_service, green_instance, channel_account):
    service, _, _, channel_account_repo, instance_repo = make_service(
        instance=green_instance,
        channel_account=channel_account,
    )

    with patch("services.cleanup_service.decrypt", return_value=DECRYPTED_GREEN_CREDS), \
         patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    assert mock_client.post.call_count == 2
    calls = [str(c.args[0]) for c in mock_client.post.call_args_list]
    assert any("clearMessagesQueue" in c for c in calls)
    assert any("logout" in c for c in calls)


# --- whatsapp_green: инстанс освобождается в БД ---

@pytest.mark.asyncio
async def test_green_instance_freed(line_id, make_service, green_instance, channel_account):
    service, _, _, _, instance_repo = make_service(
        instance=green_instance,
        channel_account=channel_account,
    )

    with patch("services.cleanup_service.decrypt", return_value=DECRYPTED_GREEN_CREDS), \
         patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(status_code=200)

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    instance_repo.update.assert_awaited_once_with(
        green_instance,
        external_id=None,
        allocated_to_line_id=None,
        status="free",
    )


# --- whatsapp_green: channel_account удаляется ---

@pytest.mark.asyncio
async def test_green_channel_account_deleted(line_id, make_service, green_instance, channel_account):
    service, _, _, channel_account_repo, _ = make_service(
        instance=green_instance,
        channel_account=channel_account,
    )

    with patch("services.cleanup_service.decrypt", return_value=DECRYPTED_GREEN_CREDS), \
         patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = MagicMock(status_code=200)

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    channel_account_repo.delete.assert_awaited_once_with(channel_account)
    channel_account_repo.update.assert_not_awaited()


# --- whatsapp_green: нет инстанса — API не вызывается ---

@pytest.mark.asyncio
async def test_green_no_instance_skips_api(line_id, make_service, channel_account):
    service, _, _, _, _ = make_service(
        instance=None,
        channel_account=channel_account,
    )

    with patch("services.cleanup_service.decrypt", return_value=DECRYPTED_GREEN_CREDS), \
         patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    mock_client.post.assert_not_awaited()


# --- whatsapp_green: нет токена — API не вызывается, инстанс всё равно освобождается ---

@pytest.mark.asyncio
async def test_green_no_token_skips_api_but_frees_instance(line_id, make_service, green_instance):
    acc = MagicMock()
    acc.credentials_encrypted = None
    service, _, _, _, instance_repo = make_service(
        instance=green_instance,
        channel_account=acc,
    )

    with patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    mock_client.post.assert_not_awaited()
    instance_repo.update.assert_awaited_once()


# --- whatsapp_green: HTTP ошибка не роняет cleanup ---

@pytest.mark.asyncio
async def test_green_api_error_doesnt_raise(line_id, make_service, green_instance, channel_account):
    service, _, _, _, instance_repo = make_service(
        instance=green_instance,
        channel_account=channel_account,
    )

    with patch("services.cleanup_service.decrypt", return_value=DECRYPTED_GREEN_CREDS), \
         patch("services.cleanup_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.side_effect = Exception("connection timeout")

        await service.cleanup_line(line_id, channel_type="whatsapp_green")

    instance_repo.update.assert_awaited_once()


# --- не green: channel_account обновляется, не удаляется ---

@pytest.mark.asyncio
async def test_non_green_channel_account_updated(line_id, make_service, channel_account):
    service, _, _, channel_account_repo, _ = make_service(
        channel_account=channel_account,
    )

    await service.cleanup_line(line_id, channel_type="telegram_user")

    channel_account_repo.update.assert_awaited_once_with(
        channel_account,
        session_string=None,
        credentials_encrypted=None,
        bot_token=None,
        connection_status="disconnected",
    )
    channel_account_repo.delete.assert_not_awaited()


# --- медиа удаляются из S3 ---

@pytest.mark.asyncio
async def test_media_deleted_from_s3(line_id, make_service):
    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    service, _, message_repo, _, _ = make_service(conversations=[conversation])
    message_repo.get_media_ids_by_conversation.return_value = ["media-1", "media-2"]

    await service.cleanup_line(line_id)

    assert service.s3.remove_object.call_count == 2