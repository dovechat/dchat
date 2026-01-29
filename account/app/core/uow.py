from sqlalchemy.ext.asyncio import AsyncSession
from models.tenants import Membership, Tenant
from app.repositories.tenant_repo import TenantRepository
from app.repositories.membership_repo import MembershipRepository

class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()

class TenantMembershipUoW(UnitOfWork):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
        # MembershipRepository needs model AND session
        self.tenants = TenantRepository(self.session)
        self.memberships = MembershipRepository(Membership, self.session)