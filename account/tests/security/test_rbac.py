import uuid
import pytest


class TestTenantRBAC:

    async def test_get_tenant_wrong_tenant_403(self, client, token_with_tenant, test_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/tenant/{foreign_tenant_id}",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Token tenant_id mismatch"

    async def test_get_tenant_own_tenant_200(self, client, token_with_tenant, test_tenant):
        resp = await client.get(
            f"/api/v1/tenant/{test_tenant.id}",
            headers=token_with_tenant,
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_tenant.id)

    async def test_update_tenant_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.patch(
            f"/api/v1/tenant/{foreign_tenant_id}",
            json={"name": "hacked"},
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_delete_tenant_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.delete(
            f"/api/v1/tenant/{foreign_tenant_id}",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_update_banking_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.patch(
            f"/api/v1/tenant/{foreign_tenant_id}/banking/ru",
            json={},
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_crm_settings_get_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/tenant/{foreign_tenant_id}/crm-settings",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Token tenant_id mismatch"


class TestLineRBAC:

    async def test_list_lines_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/tenants/{foreign_tenant_id}/lines/",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_list_lines_own_tenant_200(self, client, token_with_tenant, test_tenant):
        resp = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/lines/",
            headers=token_with_tenant,
        )

        assert resp.status_code == 200

    async def test_get_line_wrong_tenant_403(self, client, token_with_tenant, test_line):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/tenants/{foreign_tenant_id}/lines/{test_line.id}",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_create_line_wrong_tenant_403(self, client, token_with_tenant):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.post(
            f"/api/v1/tenants/{foreign_tenant_id}/lines/",
            json={"name": "hacked line"},
            headers=token_with_tenant,
        )

        assert resp.status_code == 403

    async def test_delete_line_wrong_tenant_403(self, client, token_with_tenant, test_line):
        foreign_tenant_id = uuid.uuid4()

        resp = await client.delete(
            f"/api/v1/tenants/{foreign_tenant_id}/lines/{test_line.id}",
            headers=token_with_tenant,
        )

        assert resp.status_code == 403