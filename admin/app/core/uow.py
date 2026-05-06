"""Unit of Work for admin service."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant_repo import AdminTenantRepository, AdminUserRepository
from app.repositories.line_repo import AdminChannelAccountRepository, AdminLineRepository
from app.repositories.instance_repo import AdminInstanceRepository
from app.repositories.billing_repo import AdminBillingRepository
from app.repositories.audit_repo import AdminAuditRepository
from repo.membership_repo import MembershipRepository


class AdminUnitOfWork:
    """
    Объединяет все репозитории в рамках одной сессии БД.
    Использовать через async with или явно передавать сессию.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

        self.tenants = AdminTenantRepository(session)
        self.lines = AdminLineRepository(session)
        self.channels = AdminChannelAccountRepository(session)
        self.instances = AdminInstanceRepository(session)
        self.billing = AdminBillingRepository(session)
        self.audit = AdminAuditRepository(session)
        self.users = AdminUserRepository(session)
        self.memberships = MembershipRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()