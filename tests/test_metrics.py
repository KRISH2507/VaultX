import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint_scraped(async_client: AsyncClient):
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    content = response.text

    # Verify custom metrics are registered and exposed
    assert "vaultx_transfers_total" in content
    assert "vaultx_transfer_duration_seconds" in content
    assert "vaultx_active_transfer_locks" in content
