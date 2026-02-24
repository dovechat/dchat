# tests/unit/test_members.py
import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.membership_repo import MembershipRepository
from app.repositories.permission_repo import PermissionRepository
from app.schemas.member_schemas import MemberCreate, LinePermissionCreate
from app.services.member_service import MemberService
from models.tenants import Membership, ResourcePermission, User
from tests.conftest import get_test_db


@pytest.mark.asyncio
async def test_add_member(client: AsyncClient, token_with_tenant: dict, test_tenant, temp_user):
    """Test adding a member to tenant"""
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members",
        json={"email": temp_user.email, "role": "member"},
        headers=token_with_tenant
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(temp_user.id)
    assert data["role"] == "member"
    assert data["tenant_id"] == str(test_tenant.id)


@pytest.mark.asyncio
async def test_list_members(client: AsyncClient, token_with_tenant: dict, test_tenant, test_user):
    """Test listing tenant members"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/members",
        headers=token_with_tenant
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(m["user_id"] == str(test_user.id) for m in data)


@pytest.mark.asyncio
async def test_remove_member(client: AsyncClient, token_with_tenant: dict, test_tenant, temp_user):
    """Test removing a member"""
    # Сначала добавляем
    add_resp = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members",
        json={"email": temp_user.email, "role": "member"},
        headers=token_with_tenant
    )
    assert add_resp.status_code == 201

    # Удаляем
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/{temp_user.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204

    # Проверяем что нет в списке
    list_resp = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/members",
        headers=token_with_tenant
    )
    assert not any(m["user_id"] == str(temp_user.id) for m in list_resp.json())


@pytest.mark.asyncio
async def test_add_line_permission(client: AsyncClient, token_with_tenant: dict, test_tenant, test_user, test_line):
    """Test granting line access"""
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions",
        json={
            "user_id": str(test_user.id),
            "line_id": str(test_line.id),
            "action": "member"
        },
        headers=token_with_tenant
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(test_user.id)
    assert data["line_id"] == str(test_line.id)
    assert data["action"] == "member"


@pytest.mark.asyncio
async def test_remove_line_permission(client: AsyncClient, token_with_tenant: dict, test_tenant, test_user, test_line):
    """Test revoking line access"""
    # Сначала выдадим разрешение
    add_resp = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions",
        json={
            "user_id": str(test_user.id),
            "line_id": str(test_line.id),
            "action": "send"
        },
        headers=token_with_tenant
    )
    assert add_resp.status_code == 201

    # Отзываем через DELETE с path параметрами
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions/{test_user.id}/{test_line.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204


# Unit tests for repositories
@pytest.mark.asyncio
async def test_member_repo_get_by_user_and_tenant(test_user, test_tenant):
    """Test MembershipRepository.get_by_user_and_tenant"""
    async with get_test_db() as db:
        repo = MembershipRepository(db)
        result = await repo.get_by_user_and_tenant(test_user.id, test_tenant.id)
        assert result is not None
        assert result.user_id == test_user.id
        assert result.tenant_id == test_tenant.id


@pytest.mark.asyncio
async def test_member_repo_get_by_tenant(test_tenant):
    """Test MembershipRepository.get_by_tenant"""
    async with get_test_db() as db:
        repo = MembershipRepository(db)
        results = await repo.get_by_tenant(test_tenant.id)
        assert len(results) >= 1
        assert any(m.tenant_id == test_tenant.id for m in results)


@pytest.mark.asyncio
async def test_permission_repo_get_by_user_and_resource(test_user, test_line, test_tenant):
    """Test PermissionRepository.get_by_user_and_resource"""
    async with get_test_db() as db:
        # Создаём permission
        perm = ResourcePermission(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            resource_type="line",
            resource_id=test_line.id,
            action="member"
        )
        db.add(perm)
        await db.commit()

        repo = PermissionRepository(db)
        result = await repo.get_by_user_and_resource(
            user_id=test_user.id,
            resource_type="line",
            resource_id=test_line.id
        )
        assert result is not None
        assert result.action == "member"