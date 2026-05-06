import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenants import Membership
from repo.base import BaseRepository
from app.schemas.tenant_schemas import MembershipCreate


class MembershipRepository(BaseRepository[Membership]):
    """Repository for managing memberships."""
    def __init__(self, session: AsyncSession):
        super().__init__(Membership, session)

    async def create_membership(self, data: MembershipCreate) -> Membership:
        """Create new membership."""
        return await self.create(**data.model_dump())

    async def get_by_user_and_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[Membership]:
        """Get membership by user and tenant."""
        query = select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_tenant(
            self,
            tenant_id: uuid.UUID,
            skip: int = 0,
            limit: int = 100,
            role: Optional[str] = None
    ) -> List[tuple]:
        from models.tenants import User
        query = (
            select(Membership, User.email)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id)
        )
        if role:
            query = query.where(Membership.role == role)
        result = await self.session.execute(query.offset(skip).limit(limit))
        return result.all()

    async def delete_by_user_and_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Delete membership by user and tenant."""
        membership = await self.get_by_user_and_tenant(user_id, tenant_id)
        if membership:
            await self.delete(membership)