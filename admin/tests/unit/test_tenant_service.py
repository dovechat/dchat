"""Unit tests for AdminTenantService."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.tenant_service import AdminTenantService
from app.schemas.admin_schemas import SetUserStatusRequest, ResetPasswordRequest, UserStatus


def make_uow(
    *,
    user=None,
    users=None,
    total=0,
):
    """Фабрика мок-UoW для тестов tenant service."""
    uow = MagicMock()
    uow.commit = AsyncMock()

    uow.tenants.get_user = AsyncMock(return_value=user)
    uow.tenants.get_all_users = AsyncMock(return_value=users or [])
    uow.tenants.count_users = AsyncMock(return_value=total)
    uow.tenants.set_user_status = AsyncMock(side_effect=lambda u, s: setattr(u, "status", s) or u)
    uow.tenants.set_user_password_hash = AsyncMock(side_effect=lambda u, h: setattr(u, "password_hash", h) or u)

    uow.audit.log = AsyncMock()

    return uow


def make_user(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", uuid4())
    user.email = kwargs.get("email", "test@example.com")
    user.role = kwargs.get("role", "support")
    user.status = kwargs.get("status", "active")
    user.created_at = None
    return user


class TestListUsers:

    async def test_returns_list_and_total(self):
        users = [make_user(), make_user()]
        uow = make_uow(users=users, total=2)
        service = AdminTenantService(uow)

        result = await service.list_users(
            skip=0, limit=100,
            role=None, status=None, email=None,
            actor_id=uuid4(),
        )

        assert result.total == 2
        assert len(result.items) == 2

    async def test_audit_logged(self):
        uow = make_uow(users=[], total=0)
        service = AdminTenantService(uow)
        actor = uuid4()

        await service.list_users(
            skip=0, limit=10,
            role="support", status=None, email=None,
            actor_id=actor,
        )

        uow.audit.log.assert_called_once()
        uow.commit.assert_called_once()

    async def test_empty_result(self):
        uow = make_uow(users=[], total=0)
        service = AdminTenantService(uow)

        result = await service.list_users(
            skip=0, limit=100,
            role=None, status=None, email=None,
            actor_id=uuid4(),
        )

        assert result.total == 0
        assert result.items == []


class TestGetUser:

    async def test_returns_user(self):
        user = make_user()
        uow = make_uow(user=user)
        service = AdminTenantService(uow)

        result = await service.get_user(user.id, actor_id=uuid4())

        assert result.id == user.id

    async def test_raises_404_when_not_found(self):
        uow = make_uow(user=None)
        service = AdminTenantService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_user(uuid4(), actor_id=uuid4())

        assert exc_info.value.status_code == 404


class TestSetUserStatus:

    async def test_changes_status(self):
        user = make_user(status="active")
        uow = make_uow(user=user)
        service = AdminTenantService(uow)

        result = await service.set_user_status(
            user.id,
            SetUserStatusRequest(status=UserStatus.suspended),
            actor_id=uuid4(),
        )

        uow.tenants.set_user_status.assert_called_once_with(user, "suspended")
        assert "suspended" in result.message

    async def test_raises_404_when_not_found(self):
        uow = make_uow(user=None)
        service = AdminTenantService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.set_user_status(
                uuid4(),
                SetUserStatusRequest(status=UserStatus.suspended),
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 404

    async def test_audit_logged_with_old_and_new_status(self):
        user = make_user(status="active")
        uow = make_uow(user=user)
        service = AdminTenantService(uow)

        await service.set_user_status(
            user.id,
            SetUserStatusRequest(status=UserStatus.suspended),
            actor_id=uuid4(),
        )

        call_kwargs = uow.audit.log.call_args.kwargs
        assert call_kwargs["details"]["old_status"] == "active"
        assert call_kwargs["details"]["new_status"] == "suspended"


class TestResetPassword:

    async def test_updates_password_hash(self):
        user = make_user()
        uow = make_uow(user=user)
        service = AdminTenantService(uow)

        result = await service.reset_password(
            user.id,
            ResetPasswordRequest(new_password="newpassword123"),
            actor_id=uuid4(),
        )

        uow.tenants.set_user_password_hash.assert_called_once()
        assert "reset" in result.message.lower()

    async def test_raises_404_when_not_found(self):
        uow = make_uow(user=None)
        service = AdminTenantService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.reset_password(
                uuid4(),
                ResetPasswordRequest(new_password="newpassword123"),
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 404

    async def test_audit_logged(self):
        user = make_user()
        uow = make_uow(user=user)
        service = AdminTenantService(uow)
        actor = uuid4()

        await service.reset_password(
            user.id,
            ResetPasswordRequest(new_password="newpassword123"),
            actor_id=actor,
        )

        call_kwargs = uow.audit.log.call_args.kwargs
        assert call_kwargs["action"] == "reset_password"
        assert call_kwargs["resource_id"] == user.id