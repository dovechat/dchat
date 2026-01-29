from models.tenants import Membership
from repo.base import BaseRepository
from app.schemas.tenant_schemas import MembershipCreate

class MembershipRepository(BaseRepository[Membership]):
    """Repository for managing memberships."""

    async def create_membership(
        self,
        data: MembershipCreate,
    ) -> Membership:
        """Create new membership."""
        return await self.create(
            **data.model_dump()
        )