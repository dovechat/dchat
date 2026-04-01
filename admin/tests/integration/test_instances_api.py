"""Integration tests for admin instances API."""
from uuid import uuid4
import pytest


class TestListInstancesAPI:

    async def test_admin_can_list_instances(self, client, admin_headers):
        response = await client.get("/api/v1/admin/instances", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "idle_count" in data
        assert "allocated_count" in data

    async def test_filter_by_status(self, client, admin_headers, idle_instance):
        response = await client.get(
            "/api/v1/admin/instances",
            params={"status": "idle"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [i["id"] for i in response.json()["items"]]
        assert str(idle_instance.id) in ids

    async def test_member_gets_403(self, client, member_headers):
        response = await client.get("/api/v1/admin/instances", headers=member_headers)

        assert response.status_code == 403


class TestGetInstanceAPI:

    async def test_get_existing_instance(self, client, admin_headers, idle_instance):
        response = await client.get(
            f"/api/v1/admin/instances/{idle_instance.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(idle_instance.id)

    async def test_get_nonexistent_returns_404(self, client, admin_headers):
        response = await client.get(
            f"/api/v1/admin/instances/{uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestCreateInstanceAPI:

    async def test_create_new_instance(self, client, admin_headers):
        response = await client.post(
            "/api/v1/admin/instances",
            json={"provider": "green", "external_id": f"new-ext-{uuid4()}"},
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "idle"
        assert data["provider"] == "green"

    async def test_duplicate_external_id_returns_409(self, client, admin_headers, idle_instance):
        response = await client.post(
            "/api/v1/admin/instances",
            json={"provider": idle_instance.provider.value, "external_id": idle_instance.external_id},
            headers=admin_headers,
        )

        assert response.status_code == 409


class TestCleanInstanceAPI:

    async def test_clean_allocated_instance(self, client, admin_headers, allocated_instance):
        response = await client.post(
            f"/api/v1/admin/instances/{allocated_instance.id}/clean",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "cleaned" in response.json()["message"].lower()

    async def test_clean_idle_instance(self, client, admin_headers, idle_instance):
        """Очистка idle инстанса — идемпотентна, не должна падать."""
        response = await client.post(
            f"/api/v1/admin/instances/{idle_instance.id}/clean",
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_clean_nonexistent_returns_404(self, client, admin_headers):
        response = await client.post(
            f"/api/v1/admin/instances/{uuid4()}/clean",
            headers=admin_headers,
        )

        assert response.status_code == 404


class TestBulkCleanAPI:

    async def test_bulk_clean_multiple(self, client, admin_headers, idle_instance, allocated_instance):
        response = await client.post(
            "/api/v1/admin/instances/bulk-clean",
            json={"instance_ids": [str(idle_instance.id), str(allocated_instance.id)]},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "2" in response.json()["message"]

    async def test_bulk_clean_with_missing_ids(self, client, admin_headers, idle_instance):
        missing = uuid4()
        response = await client.post(
            "/api/v1/admin/instances/bulk-clean",
            json={"instance_ids": [str(idle_instance.id), str(missing)]},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert str(missing) in response.json()["message"]

    async def test_empty_list_returns_422(self, client, admin_headers):
        response = await client.post(
            "/api/v1/admin/instances/bulk-clean",
            json={"instance_ids": []},
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestDeleteInstanceAPI:

    async def test_delete_idle_instance(self, client, admin_headers):
        # Создаём отдельный инстанс, чтобы не ломать фикстуры
        create_resp = await client.post(
            "/api/v1/admin/instances",
            json={"provider": "green", "external_id": f"to-delete-{uuid4()}"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201
        instance_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/admin/instances/{instance_id}",
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_delete_allocated_returns_409(self, client, admin_headers, allocated_instance):
        response = await client.delete(
            f"/api/v1/admin/instances/{allocated_instance.id}",
            headers=admin_headers,
        )

        assert response.status_code == 409

    async def test_delete_nonexistent_returns_404(self, client, admin_headers):
        response = await client.delete(
            f"/api/v1/admin/instances/{uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404