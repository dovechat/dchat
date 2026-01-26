import pytest
import asyncio
import uuid
import random

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