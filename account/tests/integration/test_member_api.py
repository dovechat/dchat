# tests/integration/test_member_api.py
import pytest
from httpx import AsyncClient
from uuid import uuid4

from tests.conftest import get_test_db
from models.tenants import Membership, ResourcePermission


@pytest.mark.asyncio
async def test_add_member_integration(client: AsyncClient, token_with_tenant: dict, test_tenant, temp_user):
    """Интеграционный тест добавления сотрудника"""
    # Добавляем
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

    # Проверяем в БД
    async with get_test_db() as db:
        from models.tenants import Membership
        membership = await db.get(Membership, data["id"])
        assert membership is not None
        assert membership.user_id == temp_user.id
        assert membership.tenant_id == test_tenant.id

    # Удаляем за собой
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/{temp_user.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_list_members_integration(client: AsyncClient, token_with_tenant: dict, test_tenant, test_user):
    """Интеграционный тест списка сотрудников"""
    response = await client.get(
        f"/api/v1/tenants/{test_tenant.id}/members",
        headers=token_with_tenant
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(m["user_id"] == str(test_user.id) for m in data)


@pytest.mark.asyncio
async def test_remove_member_integration(client: AsyncClient, token_with_tenant: dict, test_tenant, temp_user):
    """Интеграционный тест удаления сотрудника"""
    # Сначала добавляем
    add_resp = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members",
        json={"email": temp_user.email, "role": "member"},
        headers=token_with_tenant
    )
    assert add_resp.status_code == 201
    member_id = add_resp.json()["id"]

    # Удаляем
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/{temp_user.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204

    # Проверяем что удалилось из БД
    async with get_test_db() as db:
        membership = await db.get(Membership, member_id)
        assert membership is None


@pytest.mark.asyncio
async def test_add_line_permission_integration(
    client: AsyncClient, 
    token_with_tenant: dict, 
    test_tenant, 
    test_user, 
    test_line
):
    """Тест выдачи доступа к линии"""
    # Создаём
    response = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions",
        json={
            "user_id": str(test_user.id),
            "line_id": str(test_line.id),
            "action": "send"
        },
        headers=token_with_tenant
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(test_user.id)
    assert data["line_id"] == str(test_line.id)

    # Проверяем в БД
    async with get_test_db() as db:
        from sqlalchemy import select
        from models.tenants import ResourcePermission
        query = select(ResourcePermission).where(
            ResourcePermission.user_id == test_user.id,
            ResourcePermission.resource_id == test_line.id
        )
        result = await db.execute(query)
        perm = result.scalar_one_or_none()
        assert perm is not None

    # Удаляем за собой
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions/{test_user.id}/{test_line.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_line_permission_integration(
    client: AsyncClient, 
    token_with_tenant: dict, 
    test_tenant, 
    test_user, 
    test_line
):
    """Тест отзыва доступа к линии"""
    # Сначала создаём через API
    create_resp = await client.post(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions",
        json={
            "user_id": str(test_user.id),
            "line_id": str(test_line.id),
            "action": "send"
        },
        headers=token_with_tenant
    )
    assert create_resp.status_code == 201

    # Отзываем
    del_resp = await client.delete(
        f"/api/v1/tenants/{test_tenant.id}/members/line-permissions/{test_user.id}/{test_line.id}",
        headers=token_with_tenant
    )
    assert del_resp.status_code == 204

    # Проверяем что удалилось
    async with get_test_db() as db:
        from sqlalchemy import select
        from models.tenants import ResourcePermission
        query = select(ResourcePermission).where(
            ResourcePermission.user_id == test_user.id,
            ResourcePermission.resource_id == test_line.id
        )
        result = await db.execute(query)
        perm = result.scalar_one_or_none()
        assert perm is None