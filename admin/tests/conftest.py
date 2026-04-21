import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core.config import settings
from core.database import engine
from core.security import create_access_token
from models.tenants import AuditLog, Membership, UserRole, Tenant, TenantPayment, TenantStatus, User
from models.lines import ChannelAccount, Line, Instance, InstanceStatus
from models.billing import BalanceLedger, LedgerOperationType

test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
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
async def cleanup_engines():
    yield
    await engine.dispose()
    await test_engine.dispose()


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(
        base_url=f"http://{settings.app_host}:{settings.adm_app_port}",
        timeout=10.0,
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

@pytest.fixture
async def admin_user():
    """Пользователь с ролью admin."""
    async with get_test_db() as session:
        user = User(
            email=f"admin-{uuid4()}@example.com",
            password_hash="fake_hasssh",
            role="admin",
            status="active",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user

        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.commit()


@pytest.fixture
async def regular_user():
    """Обычный пользователь с ролью member."""
    async with get_test_db() as session:
        user = User(
            email=f"user-{uuid4()}@example.com",
            password_hash="fake_hash",
            role=UserRole.user,
            status="active",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user

        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.commit()


@pytest.fixture
async def blocked_user():
    """Заблокированный пользователь."""
    async with get_test_db() as session:
        user = User(
            email=f"blocked-{uuid4()}@example.com",
            password_hash="fake_hash",
            role=UserRole.user,
            status="suspended",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user

        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.commit()


# ---------------------------------------------------------------------------
# Токены
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_headers(admin_user):
    """Заголовки с валидным admin JWT."""
    token = create_access_token(subject=str(admin_user.id), role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_headers(regular_user):
    """Заголовки с JWT обычного пользователя (для проверки 403)."""
    token = create_access_token(subject=str(regular_user.id), role=UserRole.user.value)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Тенанты
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_tenant(admin_user):
    async with get_test_db() as session:
        tenant = Tenant(
            name="Test Company",
            payment=TenantPayment.acquiring,
            status=TenantStatus.active,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        membership = Membership(
            user_id=admin_user.id,
            tenant_id=tenant.id,
            role="owner",
        )
        session.add(membership)
        await session.commit()

        yield tenant

        async with get_test_db() as s:
            obj = await s.get(Tenant, tenant.id)
            if obj:
                await s.delete(obj)
                await s.commit()


# ---------------------------------------------------------------------------
# Линии
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_line(test_tenant):
    async with get_test_db() as session:
        line = Line(
            tenant_id=test_tenant.id,
            name="Test WhatsApp Line",
            status="active",
            is_demo=False,
            connection_state={"status": "not_connected"},
        )
        session.add(line)
        await session.flush()

        channel = ChannelAccount(
            line_id=line.id,
            channel_type="whatsapp_green",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            credentials_encrypted={},
        )
        session.add(channel)
        await session.commit()
        await session.refresh(line)
        yield line

        async with get_test_db() as s:
            obj = await s.get(Line, line.id)
            if obj:
                await s.delete(obj)
                await s.commit()


@pytest.fixture
async def expired_line(test_tenant):
    async with get_test_db() as session:
        line = Line(
            tenant_id=test_tenant.id,
            name="Expired Line",
            status="expired",
            is_demo=False,
            connection_state={},
        )
        session.add(line)
        await session.flush()

        channel = ChannelAccount(
            line_id=line.id,
            channel_type="telegram_bot",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            credentials_encrypted={},
        )
        session.add(channel)
        await session.commit()
        await session.refresh(line)
        yield line

        async with get_test_db() as s:
            obj = await s.get(Line, line.id)
            if obj:
                await s.delete(obj)
                await s.commit()


# ---------------------------------------------------------------------------
# Инстансы
# ---------------------------------------------------------------------------

@pytest.fixture
async def idle_instance():
    async with get_test_db() as session:
        instance = Instance(
            provider="green",
            external_id=f"test-idle-{uuid4()}",
            status=InstanceStatus.idle,
        )
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        yield instance

        async with get_test_db() as s:
            obj = await s.get(Instance, instance.id)
            if obj:
                await s.delete(obj)
                await s.commit()


@pytest.fixture
async def allocated_instance(test_line):
    async with get_test_db() as session:
        instance = Instance(
            provider="green",
            external_id=f"test-allocated-{uuid4()}",
            status=InstanceStatus.busy,
            allocated_to_line_id=test_line.id,
        )
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        yield instance

        async with get_test_db() as s:
            obj = await s.get(Instance, instance.id)
            if obj:
                await s.delete(obj)
                await s.commit()


# ---------------------------------------------------------------------------
# Биллинг
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_ledger_entry(test_tenant):
    async with get_test_db() as session:
        entry = BalanceLedger(
            tenant_id=test_tenant.id,
            amount=100.00,
            balance_type="main",
            operation_type=LedgerOperationType.deposit,
            description="Test deposit",
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        yield entry

        async with get_test_db() as s:
            obj = await s.get(BalanceLedger, entry.id)
            if obj:
                await s.delete(obj)
                await s.commit()