"""Admin repository for tenants and users."""
from uuid import UUID
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repo.base import BaseRepository
from models.tenants import User, Membership


class AdminTenantRepository(BaseRepository[User]):
    """Репозиторий пользователей для нужд админки."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_all_users(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        role: str | None = None,
        status: str | None = None,
        email: str | None = None,
    ) -> list[User]:
        filters: dict[str, Any] = {}
        if role:
            filters["role"] = role
        if status:
            filters["status"] = status
        if email:
            filters["email"] = email
        return await self.get_multi(skip=skip, limit=limit, filters=filters)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.get_by_id(user_id)

    async def set_user_status(self, user: User, new_status: str) -> User:
        return await self.update(user, status=new_status)

    async def set_user_password_hash(self, user: User, password_hash: str) -> User:
        return await self.update(user, password_hash=password_hash)

    async def count_users(
        self,
        role: str | None = None,
        status: str | None = None,
    ) -> int:
        filters: dict[str, Any] = {}
        if role:
            filters["role"] = role
        if status:
            filters["status"] = status
        return await self.count(filters=filters)