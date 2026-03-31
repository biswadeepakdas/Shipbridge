"""Tests for observability — structured logging, trace IDs, request middleware."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_response_includes_trace_id(client: AsyncClient) -> None:
    """Every response includes X-Trace-ID header for correlation."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "x-trace-id" in response.headers
    assert len(response.headers["x-trace-id"]) == 16


@pytest.mark.asyncio
async def test_custom_trace_id_echoed_back(client: AsyncClient) -> None:
    """Client-provided X-Trace-ID is echoed back in response."""
    custom_trace = "abc123def4567890"
    response = await client.get("/health", headers={"X-Trace-ID": custom_trace})
    assert response.headers["x-trace-id"] == custom_trace


@pytest.mark.asyncio
async def test_trace_id_unique_per_request(client: AsyncClient) -> None:
    """Each request without custom trace ID gets a unique one."""
    resp1 = await client.get("/health")
    resp2 = await client.get("/health")
    trace1 = resp1.headers["x-trace-id"]
    trace2 = resp2.headers["x-trace-id"]
    assert trace1 != trace2


@pytest.mark.asyncio
async def test_error_response_includes_trace_id(client: AsyncClient) -> None:
    """Error responses also include trace IDs for debugging."""
    response = await client.get("/api/v1/auth/api-keys")  # 401 — no auth
    assert response.status_code == 401
    assert "x-trace-id" in response.headers


@pytest.mark.asyncio
async def test_sentry_setup_skipped_without_dsn(client: AsyncClient) -> None:
    """Sentry setup is skipped gracefully when DSN is not configured."""
    # This test verifies the app boots without Sentry DSN (which is the test default).
    # If Sentry init crashed on empty DSN, the app wouldn't start and this test would fail.
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_otel_setup_skipped_without_endpoint(client: AsyncClient) -> None:
    """OpenTelemetry setup is skipped gracefully when OTLP endpoint is not configured."""
    # Same principle — if OTEL init crashed on empty endpoint, app wouldn't boot.
    response = await client.get("/health")
    assert response.status_code == 200
