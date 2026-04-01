"""Integration tests for admin lines API."""
from uuid import uuid4
import pytest


class TestListLinesAPI:

    async def test_admin_can_list_lines(self, client, admin_headers):
        response = await client.get("/api/v1/admin/lines", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    async def test_filter_by_tenant(self, client, admin_headers, test_line, test_tenant):
        response = await client.get(
            "/api/v1/admin/lines",
            params={"tenant_id": str(test_tenant.id)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [l["id"] for l in response.json()["items"]]
        assert str(test_line.id) in ids

    async def test_filter_by_status(self, client, admin_headers, expired_line):
        response = await client.get(
            "/api/v1/admin/lines",
            params={"status": "expired"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [l["id"] for l in response.json()["items"]]
        assert str(expired_line.id) in ids

    async def test_member_gets_403(self, client, member_headers):
        response = await client.get("/api/v1/admin/lines", headers=member_headers)

        assert response.status_code == 403


class TestGetLineAPI:

    async def test_get_existing_line(self, client, admin_headers, test_line):
        response = await client.get(
            f"/api/v1/admin/lines/{test_line.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(test_line.id)

    async def test_get_nonexistent_line(self, client, admin_headers):
        response = await client.get(
            f"/api/v1/admin/lines/{uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestSetLineStatusAPI:

    async def test_block_active_line(self, client, admin_headers, test_line):
        response = await client.patch(
            f"/api/v1/admin/lines/{test_line.id}/status",
            json={"status": "disabled"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "disabled" in response.json()["message"]

    async def test_activate_expired_line(self, client, admin_headers, expired_line):
        response = await client.patch(
            f"/api/v1/admin/lines/{expired_line.id}/status",
            json={"status": "active"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_invalid_status_returns_422(self, client, admin_headers, test_line):
        response = await client.patch(
            f"/api/v1/admin/lines/{test_line.id}/status",
            json={"status": "unknown_status"},
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestExtendLineAPI:

    async def test_extend_active_line(self, client, admin_headers, test_line):
        response = await client.post(
            f"/api/v1/admin/lines/{test_line.id}/extend",
            json={"days": 30},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "30" in response.json()["message"] or "extended" in response.json()["message"].lower()

    async def test_extend_expired_line(self, client, admin_headers, expired_line):
        response = await client.post(
            f"/api/v1/admin/lines/{expired_line.id}/extend",
            json={"days": 7},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_zero_days_returns_422(self, client, admin_headers, test_line):
        response = await client.post(
            f"/api/v1/admin/lines/{test_line.id}/extend",
            json={"days": 0},
            headers=admin_headers,
        )

        assert response.status_code == 422

    async def test_nonexistent_line_returns_404(self, client, admin_headers):
        response = await client.post(
            f"/api/v1/admin/lines/{uuid4()}/extend",
            json={"days": 30},
            headers=admin_headers,
        )

        assert response.status_code == 404