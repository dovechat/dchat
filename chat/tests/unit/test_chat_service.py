import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.services.chat_service import ChatService
from models.messages import Conversation, Message
from models.lines import Line




@pytest.fixture
def chat_service(mock_db):
    return ChatService(mock_db)


@pytest.fixture
def test_tenant_id():
    return uuid.uuid4()

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Мокаем execute чтобы возвращал объект с scalars()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


@pytest.fixture
def test_conversation():
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.line_id = uuid.uuid4()
    conv.crm_type = "bitrix24"
    conv.crm_chat_id = "chat123"
    conv.client_phone = "+79123456789"
    conv.meta = {}
    conv.created_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)
    return conv


class TestChatService:
    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, chat_service, mock_db, test_tenant_id):
        mock_db.execute.return_value.all.return_value = []

        result = await chat_service.get_conversations(test_tenant_id)

        assert result == []
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, chat_service, mock_db, test_tenant_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await chat_service.get_conversation(uuid.uuid4(), test_tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_messages_no_access(self, chat_service, mock_db):
        # Мокаем репозитории
        chat_service.conv_repo.get_conversation_with_messages = AsyncMock(return_value=None)

        result = await chat_service.get_messages(
            conversation_id=uuid.uuid4(),
            tenant_id=uuid.uuid4()
        )

        assert result == []

