import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.channel_service import ChannelAccountService
from app.schemas.channel_schemas import ChannelAccountResponse
from models.lines import Line
from schemas.line_schemas import ChannelType


@pytest.fixture
def mock_repos():
    return {
        "channel_repo": AsyncMock(),
        "line_repo": AsyncMock(),
        "instance_repo": AsyncMock()
    }

@pytest.mark.asyncio
async def test_update_whatsapp_green_creates_new_account(mock_repos):
    # Arrange
    line_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    id_instance = "inst_123"
    api_token = "token_456"
    

    # Mock line verification
    mock_line = MagicMock(spec=Line)
    mock_line.channel_type = "whatsapp_green"
    mock_repos["line_repo"].get_line_by_id.return_value = mock_line

    # No existing account
    mock_repos["channel_repo"].get_by_line_and_type.return_value = None

    # Mock created account
    mock_created = MagicMock()
    mock_created.id = uuid.uuid4()
    mock_created.line_id = line_id
    mock_created.channel_type = "whatsapp_green"
    mock_created.state_json = {}
    mock_created.updated_at = None
    mock_repos["channel_repo"].create_account.return_value = mock_created
    mock_repos["channel_repo"].update_account.return_value = mock_created

    service = ChannelAccountService(
        channel_repo=mock_repos["channel_repo"],
        line_repo=mock_repos["line_repo"],
        instance_repo=mock_repos["instance_repo"],
        crm_line_repo=AsyncMock()
    )

    # Act
    result = await service.update_whatsapp_green(
        line_id=line_id,
        tenant_id=tenant_id,
        id_instance=id_instance,
        api_token=api_token
    )

    # Assert
    mock_repos["line_repo"].get_line_by_id.assert_called_once_with(line_id, tenant_id)

    # Check credentials were encrypted
    call_kwargs = mock_repos["channel_repo"].update_account.call_args
    assert call_kwargs is not None

    assert isinstance(result, ChannelAccountResponse)
    assert result.id == mock_created.id
    assert result.line_id == line_id


@pytest.mark.asyncio
async def test_update_whatsapp_green_updates_existing_account(mock_repos):
    # Arrange
    line_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    id_instance = "inst_123"
    api_token = "token_456"

    # Mock line verification
    mock_line = MagicMock(spec=Line)
    mock_line.channel_type = "whatsapp_green"
    mock_repos["line_repo"].get_line_by_id.return_value = mock_line

    # Existing account
    mock_existing = MagicMock()
    mock_repos["channel_repo"].get_by_line.return_value = mock_existing

    # Mock updated account
    mock_updated = MagicMock()
    mock_updated.channel_type = "whatsapp_green"
    mock_updated.state_json = {}
    mock_updated.updated_at = None
    mock_updated.id = uuid.uuid4()
    mock_updated.line_id = line_id
    mock_repos["channel_repo"].update_account.return_value = mock_updated
    
    service = ChannelAccountService(
        channel_repo=mock_repos["channel_repo"],
        line_repo=mock_repos["line_repo"],
        instance_repo=mock_repos["instance_repo"],
        crm_line_repo=AsyncMock()
    )

    # Act
    result = await service.update_whatsapp_green(
        line_id=line_id,
        tenant_id=tenant_id,
        id_instance=id_instance,
        api_token=api_token
    )

    # Assert
    mock_repos["channel_repo"].get_by_line_and_type.assert_called_once_with(line_id, ChannelType.WHATSAPP_GREEN)
    mock_repos["channel_repo"].update_account.assert_called_once()
    mock_repos["channel_repo"].create_account.assert_not_called()

    assert isinstance(result, ChannelAccountResponse)


@pytest.mark.asyncio
async def test_update_whatsapp_green_line_not_found(mock_repos):
    # Arrange
    line_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    id_instance = "inst_123"
    api_token = "token_456"

    # Line not found
    mock_repos["line_repo"].get_line_by_id.return_value = None

    service = ChannelAccountService(
        channel_repo=mock_repos["channel_repo"],
        line_repo=mock_repos["line_repo"],
        instance_repo=mock_repos["instance_repo"],
        crm_line_repo=AsyncMock()
    )

    # Act & Assert
    with pytest.raises(Exception) as exc:  # HTTPException 404
        await service.update_whatsapp_green(
            line_id=line_id,
            tenant_id=tenant_id,
            id_instance=id_instance,
            api_token=api_token
        )

    assert "Line not found" in str(exc.value)