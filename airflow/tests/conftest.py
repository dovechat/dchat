import asyncio
import contextlib
import uuid
import json
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from core.config import settings
from core.database import engine
from models.lines import Line, Instance, ChannelAccount, ChannelType, InstanceStatus, LineStatus
from infra.crypto import encrypt


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
            await session.commit()
        except Exception:
            await session.rollback()
            raise
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


# ------ lines

@pytest.fixture
async def test_line(test_tenant):
    async with get_test_db() as session:
        line = Line(
            tenant_id=test_tenant.id,
            name="Test WhatsApp Green Line",
            channel_type=ChannelType.whatsapp_green,
            status=LineStatus.active,
            is_demo=False,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            connection_state={"status": "not_connected"},
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
async def test_allocated_instance(test_line):
    async with get_test_db() as session:
        instance = Instance(
            provider="green",
            external_id=f"test_instance_{uuid.uuid4().hex[:8]}",
            status=InstanceStatus.busy,
            allocated_to_line_id=test_line.id,
        )
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        yield instance

        async with get_test_db() as session:
            obj = await session.get(Instance, instance.id)
            if obj:
                await session.delete(obj)
                await session.commit()


@pytest.fixture
async def test_channel_account(test_line):
    credentials = {"id_instance": "test_instance_12345", "api_token": "test-api-token"}
    encrypted = {"encrypted_data": encrypt(json.dumps(credentials))}

    async with get_test_db() as session:
        account = ChannelAccount(
            line_id=test_line.id,
            credentials_encrypted=encrypted,
            connection_status="connected",
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
        yield account

        async with get_test_db() as session:
            obj = await session.get(ChannelAccount, account.id)
            if obj:
                await session.delete(obj)
                await session.commit()


from models.tenants import Tenant, TenantStatus, TenantPayment

@pytest.fixture
async def test_tenant():
    async with get_test_db() as session:
        tenant = Tenant(
            name="Test Company",
            payment=TenantPayment.acquiring,
            status=TenantStatus.active,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        yield tenant

        async with get_test_db() as session:
            obj = await session.get(Tenant, tenant.id)
            if obj:
                await session.delete(obj)
                await session.commit()