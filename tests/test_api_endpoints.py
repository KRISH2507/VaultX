import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_account_creation_and_balance(async_client: AsyncClient):
    user_id = str(uuid.uuid4())
    # Create account
    create_resp = await async_client.post(
        "/api/v1/accounts",
        json={"user_id": user_id, "currency": "INR", "initial_balance": "500.00"},
    )
    assert create_resp.status_code == 201
    account = create_resp.json()
    account_id = account["id"]
    assert account["balance"] == "500.00"
    assert account["currency"] == "INR"

    # Query balance
    bal_resp = await async_client.get(f"/api/v1/accounts/{account_id}/balance")
    assert bal_resp.status_code == 200
    bal_data = bal_resp.json()
    assert bal_data["balance"] == "500.00"
    assert bal_data["version"] == 1


@pytest.mark.asyncio
async def test_transfer_endpoint_and_idempotency_retry(async_client: AsyncClient):
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    # Create Account A with 1000.00
    res_a = await async_client.post(
        "/api/v1/accounts",
        json={"user_id": user_a, "currency": "INR", "initial_balance": "1000.00"},
    )
    acc_a_id = res_a.json()["id"]

    # Create Account B with 200.00
    res_b = await async_client.post(
        "/api/v1/accounts",
        json={"user_id": user_b, "currency": "INR", "initial_balance": "200.00"},
    )
    acc_b_id = res_b.json()["id"]

    idempotency_key = "idemp-key-api-transfer-test"
    transfer_payload = {
        "source_account_id": acc_a_id,
        "destination_account_id": acc_b_id,
        "amount": "300.00",
        "currency": "INR",
        "description": "API Transfer Test",
    }

    # First Transfer Request
    tx_resp1 = await async_client.post(
        "/api/v1/transfers",
        json=transfer_payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    assert tx_resp1.status_code == 201
    tx_data1 = tx_resp1.json()
    assert tx_data1["status"] == "COMMITTED"
    assert tx_data1["amount"] == "300.00"
    assert len(tx_data1["postings"]) == 2

    # Second Transfer Request with identical key (simulating network retry storm)
    tx_resp2 = await async_client.post(
        "/api/v1/transfers",
        json=transfer_payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    # Must succeed with identical response without deducting money again!
    assert tx_resp2.status_code in [200, 201]
    tx_data2 = tx_resp2.json()
    assert tx_data2["id"] == tx_data1["id"]

    # Verify balances: Account A should be 700.00, Account B should be 500.00
    bal_a = await async_client.get(f"/api/v1/accounts/{acc_a_id}/balance")
    bal_b = await async_client.get(f"/api/v1/accounts/{acc_b_id}/balance")
    assert bal_a.json()["balance"] == "700.00"
    assert bal_b.json()["balance"] == "500.00"
