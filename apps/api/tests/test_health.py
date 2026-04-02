"""Tests for the health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    """Health endpoint returns 200 with correct response shape."""
    response = await client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["status"] in ("ok", "degraded")
    assert body["data"]["service"] == "api"
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["timestamp"] is not None
    assert body["error"] is None
    assert "checks" in body["data"]


@pytest.mark.asyncio
async def test_health_endpoint_has_dependency_checks(client: AsyncClient) -> None:
    """Health endpoint reports postgres and redis check status."""
    response = await client.get("/health")
    body = response.json()

    checks = body["data"]["checks"]
    assert "postgres" in checks
    assert "redis" in checks
    assert checks["postgres"] in ("ok", "unavailable")
    assert checks["redis"] in ("ok", "unavailable")
