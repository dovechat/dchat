import asyncio
import contextlib
from uuid import uuid4

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from core.config import settings
from core.database import engine, get_db
from core.security import create_access_token
from models.tenants import Membership, Tenant, TenantPayment, TenantStatus, User
from models.lines import Line, Instance, InstanceStatus
from app.schemas.line_schemas import ChannelType


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

@pytest.fixture
async def test_db():
    async with get_test_db() as session:
        yield session

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
            name="Test Company",
            payment=TenantPayment.acquiring,
            status=TenantStatus.active
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        # Create membership to avoid 403 Forbidden on switch
        membership = Membership(
            user_id=test_user.id,
            tenant_id=tenant.id,
            role="owner"
        )
        session.add(membership)
        await session.commit()

        yield tenant

        async with get_test_db() as session:
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


@pytest.fixture
async def token_with_tenant(client, test_user, test_tenant, token_headers):
    """Token with tenant_id after switching tenant"""
    response = await client.post(
        f"/api/v1/auth/switch-tenant",
        json={"tenant_id": str(test_tenant.id)},
        headers=token_headers
    )



    print(f"test_user {test_user.id}")
    print(f"test_tenant {test_tenant.id}")
    print(f"token_headers {token_headers}")



    assert response.status_code == 200
    new_token = response.json()["access_token"]
    print(f"new_token {new_token}")
    yield {"Authorization": f"Bearer {new_token}"}


# ------ lines

@pytest.fixture
async def test_line(test_tenant):
    """Create test line for tenant"""
    async with get_test_db() as session:
        line = Line(
            tenant_id=test_tenant.id,
            name="Test WhatsApp Line",
            channel_type=ChannelType.WHATSAPP_GREEN.value,
            status="active",
            is_demo=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            connection_state={"status": "not_connected"}
        )
        session.add(line)
        await session.commit()
        await session.refresh(line)
        yield line

        async with get_test_db() as session:
            obj = await session.get(Line, line.id)
            if obj:
                await session.delete(obj)
                await session.commit()


@pytest.fixture
async def test_instance():
    """Create test WhatsApp instance in pool"""
    async with get_test_db() as session:
        instance = Instance(
            provider="green_api",
            external_id="test_instance_12345",
            status=InstanceStatus.idle
        )
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        yield instance

        # Cleanup
        async with get_test_db() as session:
            obj = await session.get(Instance, instance.id)
            if obj:
                await session.delete(obj)
                await session.commit()


@pytest.fixture
async def test_allocated_instance(test_line):
    """Create instance allocated to test line"""
    async with get_test_db() as session:
        instance = Instance(
            provider="green_api",
            external_id="test_allocated_instance",
            status=InstanceStatus.busy,
            allocated_to_line_id=test_line.id
        )
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        yield instance

        # Cleanup
        async with get_test_db() as session:
            obj = await session.get(Instance, instance.id)
            if obj:
                await session.delete(obj)
                await session.commit()


@pytest.fixture
async def temp_user():
    """Create a temporary user and delete after test"""
    email = f"test-{uuid4()}@example.com"
    async with get_test_db() as db:
        user = User(
            email=email,
            password_hash="fake_hash_for_test",
            status="active"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        yield user
        await db.delete(user)
        await db.commit()



@pytest.fixture
async def test_line_permission(test_user, test_line, test_tenant):
    """Create a line permission and delete after test"""
    async with get_test_db() as db:
        perm = ResourcePermission(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            resource_type="line",
            resource_id=test_line.id,
            action="send"
        )
        db.add(perm)
        await db.commit()
        await db.refresh(perm)
        yield perm
        await db.delete(perm)
        await db.commit()