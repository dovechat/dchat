# app/services/member_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional
import logging

from app.repositories.membership_repo import MembershipRepository
from app.repositories.permission_repo import PermissionRepository
from repo.user import UserRepository
from app.repositories.line_repo import LineRepository
from app.schemas.member_schemas import (
    MemberCreate,
    MemberResponse,
    LinePermissionCreate,
    LinePermissionResponse
)
from infra.email.sender import ManagerSender
from models.tenants import Membership, ResourcePermission, User

log = logging.getLogger(__name__)


class MemberService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.member_repo = MembershipRepository(db)
        self.permission_repo = PermissionRepository(db)
        self.user_repo = UserRepository(db)
        self.line_repo = LineRepository(db)

    async def _create_user_and_send_invite(self, email: str) -> User:
        """Создать пользователя и отправить приглашение"""
        import secrets
        from core.security import get_password_hash

        plain_password = secrets.token_urlsafe(12)
        hashed_password = get_password_hash(plain_password)

        user = await self.user_repo.create(
            email=email,
            password_hash=hashed_password,
            status="active"
        )

        ManagerSender().send(email, plain_password)
        return user

    async def add_member(self, tenant_id: UUID, data: MemberCreate) -> MemberResponse:
        """Добавить сотрудника в тенант"""
        # Ищем пользователя по email
        user = await self.user_repo.get_by_email(data.email)

        # Если пользователя нет - создаём
        if not user:
            user = await self._create_user_and_send_invite(data.email)

        # Проверяем, не состоит ли уже
        existing = await self.member_repo.get_by_user_and_tenant(user.id, tenant_id)
        if existing:
            raise ValueError("User already member of this tenant")

        # Создаем членство
        member = await self.member_repo.create(
            user_id=user.id,
            tenant_id=tenant_id,
            role=data.role,
            is_active=True
        )

        return MemberResponse.from_orm(member)

    async def _send_invitation_email(self, email: str, password: str):
        """Отправить приглашение с паролем"""
        # Здесь вызов существующего email-сервиса
        pass

    async def list_members(self, tenant_id: UUID, skip: int, limit: int) -> List[MemberResponse]:
        """Список сотрудников тенанта"""
        members = await self.member_repo.get_by_tenant(tenant_id, skip, limit)
        return [MemberResponse.from_orm(m) for m in members]

    async def remove_member(self, tenant_id: UUID, user_id: UUID):
        """Удалить сотрудника из тенанта"""
        member = await self.member_repo.get_by_user_and_tenant(user_id, tenant_id)
        if not member:
            raise ValueError("Member not found")

        await self.member_repo.delete(member)

    async def add_line_permission(self, tenant_id: UUID, data: LinePermissionCreate) -> LinePermissionResponse:
        """Выдать доступ к линии"""
        # Проверяем, что линия принадлежит тенанту
        line = await self.line_repo.get_by_id(data.line_id)
        if not line or line.tenant_id != tenant_id:
            raise ValueError("Line not found or not in tenant")

        # Проверяем, что пользователь - сотрудник тенанта
        member = await self.member_repo.get_by_user_and_tenant(data.user_id, tenant_id)
        if not member:
            raise ValueError("User is not a member of this tenant")

        # Создаем permission
        permission = await self.permission_repo.create(
            user_id=data.user_id,
            tenant_id=tenant_id,
            resource_type="line",
            resource_id=data.line_id,
            action="member"
        )

        return LinePermissionResponse(
            user_id=permission.user_id,
            line_id=permission.resource_id,
            action=permission.action
        )

    async def get_line_permissions(self, tenant_id: UUID, user_id: UUID) -> List[LinePermissionResponse]:
        """Получить список доступов к линиям для сотрудника"""
        permissions = await self.permission_repo.get_by_user_and_resource_type(
            user_id=user_id,
            resource_type="line"
        )
        return [
            LinePermissionResponse(
                user_id=p.user_id,
                line_id=p.resource_id,
                action=p.action
            )
            for p in permissions
            if p.tenant_id == tenant_id
        ]

    async def remove_line_permission(self, tenant_id: UUID, user_id: UUID, line_id: UUID):
        """Отозвать доступ к линии"""
        permission = await self.permission_repo.get_by_user_and_resource(
            user_id=user_id,
            resource_type="line",
            resource_id=line_id
        )
        if not permission:
            raise ValueError("Permission not found")

        await self.permission_repo.delete(permission)
