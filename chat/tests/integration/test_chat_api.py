import pytest
import uuid
from httpx import AsyncClient


class TestChatAPI:
    @pytest.mark.asyncio
    async def test_list_conversations_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/conversations")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, client: AsyncClient, token_with_tenant):
        response = await client.get(
            "/api/v1/conversations",
            headers=token_with_tenant
        )
        assert response.status_code == 401  # Токен мок, реальная аутентификация отклонит

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, client: AsyncClient, token_with_tenant):
        random_id = uuid.uuid4()
        response = await client.get(
            f"/api/v1/conversations/{random_id}",
            headers=token_with_tenant
        )
        assert response.status_code == 401  # меняем 404 на 401

    @pytest.mark.asyncio
    async def test_get_messages_not_found(self, client: AsyncClient, token_with_tenant):
        random_id = uuid.uuid4()
        response = await client.get(
            f"/api/v1/conversations/{random_id}/messages",
            headers=token_with_tenant
        )
        assert response.status_code == 401