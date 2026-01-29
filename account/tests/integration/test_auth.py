import pytest
import asyncio
import uuid
import random


@pytest.mark.asyncio
async def test_verify_throttle_and_trial_status(client):
    # 1. Register new user (status: inactive)
    suffix = uuid.uuid4().hex[:6]
    payload = {
        "email": f"u_{suffix}@test.com",
        "phone": f"+{random.randint(10 ** 8, 10 ** 9)}",
        "password": "pass", "ifsms": True
    }
    reg_resp = await client.post("/api/v1/auth/register", json=payload)
    print("************ reg_resp", reg_resp)
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. First attempt: Invalid code sets 3s lock
    resp1 = await client.post("/api/v1/auth/verify", params={"code": "0000"}, headers=headers)
    assert resp1.status_code == 400

    # 3. Burst: Should get 429 within 3s window
    resp2 = await client.post("/api/v1/auth/verify", params={"code": "0000"}, headers=headers)
    assert resp2.status_code == 429

    # 4. Wait for lock to clear
    await asyncio.sleep(3.1)

    # 5. Check logic after lock is gone
    resp3 = await client.post("/api/v1/auth/verify", params={"code": "0000"}, headers=headers)
    assert resp3.status_code == 400
    assert "Invalid code" in resp3.text

    # 6. Wait again to clear lock from step 5 before final checks
    await asyncio.sleep(3.1)

    # Note: Success attempt (step 6) and Already activated (step 7) 
    # require knowing the real_code or manual DB state change.


@pytest.mark.asyncio
async def test_switch_tenant_success(client, token_headers, test_tenant):
    tenant_id = test_tenant.id

    response = await client.post(
        f"/api/v1/auth/switch-tenant/{tenant_id}",
        headers=token_headers
    )

    assert response.status_code == 200
    data = response.json()

    # Switch-tenant usually returns a new token pair, not a status string
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"





@pytest.mark.asyncio
async def test_switch_tenant_api_forbidden(client, token_headers):
    # Random UUID should return 403 as no membership exists
    random_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/auth/switch-tenant/{random_id}",
        headers=token_headers
    )
    assert response.status_code == 403