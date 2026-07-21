import asyncio
import pytest
from httpx import AsyncClient
from app.api.main import app

import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def token_with_tenant():
    """Mock token header for tests"""
    return {"Authorization": "Bearer mock-token"}