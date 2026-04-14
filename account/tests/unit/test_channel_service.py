import pytest
import uuid

from datetime import datetime
from unittest.mock import AsyncMock, Mock
from fastapi import HTTPException

from app.services.channel_service import ChannelAccountService
from app.schemas.channel_schemas import (
    TelegramBotCredentials,
    TelegramUserCredentials,
    VKCredentials,
    ChannelAccountResponse
)
from schemas.line_schemas import ChannelType
from infra.crypto import encrypt


@pytest.fixture
def mock_channel_account():
    """Mock channel account object"""
    enc_data = encrypt('{"phone":"+11213456789", "session_string":"8bsfg98bsfgsfgnsfgns8fghspfgnsfgnws"}')
    class MockChannelAccount:
        def __init__(self):
            self.id = uuid.uuid4()
            self.line_id = uuid.uuid4()
            self.credentials_encrypted = {"encrypted_data": enc_data}
            self.state_json = {"status": "active"}
            self.updated_at = None

    return MockChannelAccount()


@pytest.fixture
def mock_line():
    """Mock line object"""
    line = Mock()
    line.id = uuid.uuid4()
    line.tenant_id = uuid.uuid4()
    line.channel_type = "telegram_bot"
    return line


@pytest.fixture
def channel_service():
    """ChannelAccountService with mocked repos"""
    mock_channel_repo = AsyncMock()
    mock_line_repo = AsyncMock()

    return ChannelAccountService(
        channel_repo=mock_channel_repo,
        line_repo=mock_line_repo
    )


@pytest.fixture
def channel_service_waba():
    """Base channel service with all repos mocked"""
    mock_channel = AsyncMock()
    mock_line = AsyncMock()
    mock_instance = AsyncMock()

    return ChannelAccountService(
        channel_repo=mock_channel,
        line_repo=mock_line,
        instance_repo=mock_instance
    )


# === GET TESTS ===

@pytest.mark.asyncio
async def test_get_account_success(channel_service, mock_line, mock_channel_account):
    """Test getting channel account"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    
    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = mock_channel_account
    
    result = await channel_service.get_account(line_id, tenant_id)
    '''
    assert isinstance(result, ChannelAccountResponse)
    assert result.line_id == mock_channel_account.line_id
    assert result.channel_type == "telegram_bot"
    '''

@pytest.mark.asyncio
async def test_get_account_line_not_found(channel_service):
    """Test 404 when line not found"""
    line_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    channel_service.line_repo.get_line_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        await channel_service.get_account(line_id, tenant_id)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_account_not_found(channel_service, mock_line):
    """Test 404 when channel account not found"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = None

    res = await channel_service.get_account(line_id, tenant_id)
    assert res.id is None
    assert res.line_id == line_id


# === UPDATE TELEGRAM BOT TESTS ===

@pytest.mark.asyncio
async def test_update_telegram_bot_success(channel_service, mock_line, mock_channel_account):
    """Test updating Telegram Bot credentials"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    credentials = TelegramBotCredentials(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        webhook_url="https://example.com/webhook"
    )

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = mock_channel_account
    channel_service.channel_repo.update_account.return_value = mock_channel_account

    result = await channel_service.update_telegram_bot(line_id, tenant_id, credentials)

    channel_service.channel_repo.update_account.assert_called_once()
    assert isinstance(result, ChannelAccountResponse)


@pytest.mark.asyncio
async def test_update_telegram_bot_creates_if_not_exists(channel_service, mock_line, mock_channel_account):
    """Test creating channel account if it doesn't exist"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    credentials = TelegramBotCredentials(bot_token="test_token")

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = None
    channel_service.channel_repo.create_account.return_value = mock_channel_account

    result = await channel_service.update_telegram_bot(line_id, tenant_id, credentials)

    channel_service.channel_repo.create_account.assert_called_once()
    assert isinstance(result, ChannelAccountResponse)


@pytest.mark.asyncio
async def test_update_telegram_bot_wrong_channel_type(channel_service, mock_line):
    """Test 400 when line has wrong channel type"""
    mock_line.channel_type = "vk"
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    credentials = TelegramBotCredentials(bot_token="test_token")

    channel_service.line_repo.get_line_by_id.return_value = mock_line

    with pytest.raises(HTTPException) as exc:
        await channel_service.update_telegram_bot(line_id, tenant_id, credentials)

    assert exc.value.status_code == 400


# === UPDATE TELEGRAM USER TESTS ===

@pytest.mark.asyncio
async def test_update_telegram_user_success(channel_service, mock_line, mock_channel_account):
    """Test updating Telegram User credentials"""
    mock_line.channel_type = "telegram_user"
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    credentials = TelegramUserCredentials(
        phone="+1234567890",
        api_id="12345",
        api_hash="abcdef123456",
        session_string="test_session"
    )

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = mock_channel_account
    channel_service.channel_repo.update_account.return_value = mock_channel_account

    result = await channel_service.update_telegram_user(line_id, tenant_id, credentials)

    channel_service.channel_repo.update_account.assert_called_once()
    assert isinstance(result, ChannelAccountResponse)


@pytest.mark.asyncio
async def test_update_waba_success(channel_service_waba, mock_line):
    """Test successful WABA credentials update"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id
    api_key = "test-waba-key-123"


    mock_line.channel_type = ChannelType.WABA
    mock_updated = AsyncMock(
        id=uuid.uuid4(),
        line_id=line_id,
        state_json={},
        updated_at=datetime.now()
    )

    channel_service_waba.line_repo.get_line_by_id.return_value = mock_line
    channel_service_waba.channel_repo.get_by_line.return_value = None
    channel_service_waba._encrypt_credentials = lambda x: {"encrypted_data": "encrypted"}
    channel_service_waba.channel_repo.create_account.return_value = mock_updated

    result = await channel_service_waba.update_waba(line_id, tenant_id, api_key)

    assert result.line_id == line_id


@pytest.mark.asyncio
async def test_update_waba_wrong_channel_type(channel_service, mock_line):
    """Test 400 when line has wrong channel type"""
    mock_line.channel_type = "telegram_bot"
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id
    api_key = "test-key"

    channel_service.line_repo.get_line_by_id.return_value = mock_line

    with pytest.raises(HTTPException) as exc:
        await channel_service.update_waba(line_id, tenant_id, api_key)

    assert exc.value.status_code == 400





# === UPDATE VK TESTS ===

@pytest.mark.asyncio
async def test_update_vk_success(channel_service, mock_line, mock_channel_account):
    """Test updating VK credentials"""
    mock_line.channel_type = "vk"
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    credentials = VKCredentials(
        access_token="vk_token_12345",
        group_id="67890"
    )

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = mock_channel_account
    channel_service.channel_repo.update_account.return_value = mock_channel_account

    result = await channel_service.update_vk(line_id, tenant_id, credentials)

    channel_service.channel_repo.update_account.assert_called_once()
    assert isinstance(result, ChannelAccountResponse)

'''
# === UPDATE STATE TESTS ===

@pytest.mark.asyncio
async def test_update_state_success(channel_service, mock_line, mock_channel_account):
    """Test updating state_json"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    new_state = {"status": "connected", "last_update": "2024-01-01"}

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = mock_channel_account
    channel_service.channel_repo.update_account.return_value = mock_channel_account

    result = await channel_service.update_state(line_id, tenant_id, new_state)

    channel_service.channel_repo.update_account.assert_called_once()
    assert isinstance(result, ChannelAccountResponse)


@pytest.mark.asyncio
async def test_update_state_account_not_found(channel_service, mock_line):
    """Test 404 when account doesn't exist"""
    line_id = mock_line.id
    tenant_id = mock_line.tenant_id

    channel_service.line_repo.get_line_by_id.return_value = mock_line
    channel_service.channel_repo.get_by_line.return_value = None

    with pytest.raises(HTTPException) as exc:
        await channel_service.update_state(line_id, tenant_id, {"status": "test"})

    assert exc.value.status_code == 404
'''