"""Integration tests for admin billing and dashboard API."""
from uuid import uuid4
import pytest


class TestBillingLedgerAPI:

    async def test_admin_can_view_ledger(self, client, admin_headers):
        print("client base_url", client.base_url)
        response = await client.get("/api/v1/billing/ledger", headers=admin_headers)
        print("status", response.status_code, "body", response.text)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    async def test_filter_by_tenant(self, client, admin_headers, test_tenant, test_ledger_entry):
        response = await client.get(
            "/api/v1/billing/ledger",
            params={"tenant_id": str(test_tenant.id)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [e["id"] for e in response.json()["items"]]
        assert test_ledger_entry.id in ids

    async def test_filter_by_operation_type(self, client, admin_headers, test_ledger_entry):
        response = await client.get(
            "/api/v1/billing/ledger",
            params={"operation_type": "deposit"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_invalid_operation_type_returns_400(self, client, admin_headers):
        response = await client.get(
            "/api/v1/billing/ledger",
            params={"operation_type": "invalid_type"},
            headers=admin_headers,
        )

        assert response.status_code == 400

    async def test_member_gets_403(self, client, member_headers):
        response = await client.get("/api/v1/billing/ledger", headers=member_headers)

        assert response.status_code == 403


class TestBillingBalanceAPI:

    async def test_get_balance_for_tenant(self, client, admin_headers, test_tenant, test_ledger_entry):
        response = await client.get(
            f"/api/v1/billing/balance/{test_tenant.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "main" in data
        assert "bonus" in data
        # test_ledger_entry — deposit 100.00 на main
        assert data["main"] >= 100.0

    async def test_balance_for_tenant_without_operations(self, client, admin_headers, test_tenant):
        # Новый тенант без операций
        response = await client.get(
            f"/api/v1/billing/balance/{test_tenant.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["main"], float)
        assert isinstance(data["bonus"], float)


class TestBillingAdjustmentAPI:

    async def test_positive_adjustment(self, client, admin_headers, test_tenant):
        response = await client.post(
            f"/api/v1/billing/adjustment/{test_tenant.id}",
            json={
                "amount": "200.00",
                "balance_type": "main",
                "description": "Manual top-up by admin",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert "200" in response.json()["message"]

    async def test_negative_adjustment(self, client, admin_headers, test_tenant):
        response = await client.post(
            f"/api/v1/billing/adjustment/{test_tenant.id}",
            json={
                "amount": "-50.00",
                "balance_type": "main",
                "description": "Correction",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_bonus_balance_adjustment(self, client, admin_headers, test_tenant):
        response = await client.post(
            f"/api/v1/billing/adjustment/{test_tenant.id}",
            json={
                "amount": "25.00",
                "balance_type": "bonus",
                "description": "Bonus grant",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_invalid_balance_type_returns_422(self, client, admin_headers, test_tenant):
        response = await client.post(
            f"/api/v1/billing/adjustment/{test_tenant.id}",
            json={
                "amount": "100.00",
                "balance_type": "invalid",
                "description": "Bad request",
            },
            headers=admin_headers,
        )

        assert response.status_code == 422

    async def test_empty_description_returns_422(self, client, admin_headers, test_tenant):
        response = await client.post(
            f"/api/v1/billing/adjustment/{test_tenant.id}",
            json={
                "amount": "100.00",
                "balance_type": "main",
                "description": "",
            },
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestDashboardStatsAPI:

    async def test_admin_can_get_stats(self, client, admin_headers):
        response = await client.get("/api/v1/stats", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()

        expected_fields = [
            "total_users", "active_users", "blocked_users",
            "total_lines", "active_lines", "blocked_lines", "expired_lines",
            "total_instances", "idle_instances", "allocated_instances", "error_instances",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    async def test_stats_counts_are_non_negative(self, client, admin_headers):
        response = await client.get("/api/v1/stats", headers=admin_headers)

        assert response.status_code == 200
        for key, value in response.json().items():
            assert value >= 0, f"Negative count for {key}: {value}"

    async def test_member_gets_403(self, client, member_headers):
        response = await client.get("/api/v1/stats", headers=member_headers)

        assert response.status_code == 403


class TestDashboardAuditAPI:

    async def test_admin_can_view_audit(self, client, admin_headers):
        response = await client.get("/api/v1/audit", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    async def test_filter_by_entity_type(self, client, admin_headers):
        response = await client.get(
            "/api/v1/audit",
            params={"entity_type": "user"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_filter_by_action(self, client, admin_headers):
        response = await client.get(
            "/api/v1/audit",
            params={"action": "list_users"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    async def test_pagination(self, client, admin_headers):
        response = await client.get(
            "/api/v1/audit",
            params={"skip": 0, "limit": 5},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert len(response.json()["items"]) <= 5


class TestHealthAPI:

    async def test_health_check(self, client):
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "admin"