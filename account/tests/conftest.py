import asyncio
import contextlib

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from core.config import settings
from core.database import engine, get_db
from core.security import create_access_token
from models.tenants import Tenant, TenantPayment, TenantStatus, User

import logging

log = logging.getLogger("uvicorn.error")

test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False
)

@contextlib.asynccontextmanager
async def get_test_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@pytest.fixture(scope="session", autouse=True)
async def cleanup_all():
    yield
    await engine.dispose()
    await test_engine.dispose()

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

@pytest.fixture(scope="session", autouse=True)
async def cleanup_engines():
    yield
    # Закрываем оба движка в самом конце сессии
    await engine.dispose()
    await test_engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(base_url=f"http://{settings.app_host}:{settings.app_port}", timeout=10.0) as ac:
        yield ac



@pytest.fixture
async def test_user():
    # Use the isolated test DB manager with NullPool
    async with get_test_db() as session:
        user = User(
            email="test@example.com",
            password_hash="fake_hash_for_test",
            status="active"
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        yield user

        # Safety check: object might have been deleted in the test
        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.commit()


@pytest.fixture
async def test_tenant(test_user):
    async with get_test_db() as session:
        tenant = Tenant(
            user_id=test_user.id,
            name="Test Company",
            payment=TenantPayment.acquiring,
            status=TenantStatus.active
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        yield tenant

        # Чистим без ворнингов:
        async with get_test_db() as session:
            # merge подтянет объект, если он есть, или вернет None без ошибки
            obj = await session.get(Tenant, tenant.id)
            if obj:
                await session.delete(obj)
                await session.commit()

@pytest.fixture
async def token_headers(test_user):
    """Generate headers with a valid token for the test user."""
    # Use the correct core path as discussed
    from core.security import create_access_token

    access_token = create_access_token(
        subject=str(test_user.id), # Convert UUID to string for JWT payload
        role="admin"
    )
    return {"Authorization": f"Bearer {access_token}"}