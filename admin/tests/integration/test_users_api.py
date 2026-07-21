"""Integration tests for admin users API."""
import pytest


class TestListUsersAPI:

    async def test_admin_can_list_users(self, client, admin_headers, admin_user):
        response = await client.get("/api/v1/users", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    async def test_member_gets_403(self, client, member_headers):
        response = await client.get("/api/v1/users", headers=member_headers)

        assert response.status_code == 403

    async def test_no_token_gets_403(self, client):
        response = await client.get("/api/v1/users")

        assert response.status_code in (401, 403)

    async def test_filter_by_role(self, client, admin_headers, admin_user):
        response = await client.get(
            "/api/v1/users",
            params={"role": "admin"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        for user in data["items"]:
            assert user["role"] == "admin"

    async def test_filter_by_status(self, client, admin_headers, blocked_user):
        response = await client.get(
            "/api/v1/users",
            params={"status": "suspended"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [u["id"] for u in response.json()["items"]]
        assert str(blocked_user.id) in ids


class TestGetUserAPI:

    async def test_get_existing_user(self, client, admin_headers, regular_user):
        response = await client.get(
            f"/api/v1/users/{regular_user.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(regular_user.id)

    async def test_get_nonexistent_user(self, client, admin_headers):
        from uuid import uuid4
        response = await client.get(
            f"/api/v1/users/{uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestSetUserStatusAPI:

    async def test_block_user(self, client, admin_headers, regular_user):
        response = await client.patch(
            f"/api/v1/users/{regular_user.id}/status",
            json={"status": "suspended"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "suspended" in response.json()["message"]

    async def test_unblock_user(self, client, admin_headers, blocked_user):
        response = await client.patch(
            f"/api/v1/users/{blocked_user.id}/status",
            json={"status": "active"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_invalid_status_returns_422(self, client, admin_headers, regular_user):
        response = await client.patch(
            f"/api/v1/users/{regular_user.id}/status",
            json={"status": "nonexistent"},
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestResetPasswordAPI:

    async def test_reset_password(self, client, admin_headers, regular_user):
        response = await client.post(
            f"/api/v1/users/{regular_user.id}/reset-password",
            json={"new_password": "newpassword123"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "reset" in response.json()["message"].lower()

    async def test_short_password_returns_422(self, client, admin_headers, regular_user):
        response = await client.post(
            f"/api/v1/users/{regular_user.id}/reset-password",
            json={"new_password": "short"},
            headers=admin_headers,
        )

        assert response.status_code == 422