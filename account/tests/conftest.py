import pytest
import pytest_asyncio
from httpx import AsyncClient

@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(base_url="http://localhost:8070", timeout=10.0) as ac:
        yield ac