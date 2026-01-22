"""Repository for working with users"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenants import User
from repo.base import BaseRepository
from schemas.auth_schemas import RegisterRequest, RegisterDB

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email"""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Check if email exists"""
        return await self.exists(email=email)

    async def create_user(
        self,
        data: RegisterRequest,
    ) -> User:
        """Create new user"""
        db_data = RegisterDB(
            **data.model_dump(exclude={'password'}),
            password_hash=data.password
        )
        return await self.create(
            **db_data.model_dump()
        )

    async def activate_user(self, user_id: any):
        """Update status to active using base update logic"""
        user = await self.get_by_id(user_id)
        if user:
            return await self.update(user, status="trial")