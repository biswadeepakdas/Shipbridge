"""Tests for connector infrastructure — circuit breaker FSM, registry, vault, CRUD API."""

import time

import pytest
from httpx import AsyncClient

from app.integrations.circuit_breaker import CircuitBreaker, CircuitState
from app.integrations.registry import ConnectorRegistry
from app.integrations.vault import OAuthVault


# --- Unit tests: CircuitBreaker FSM ---

class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_stays_closed_under_threshold(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_open_blocks_requests(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

    def test_half_open_success_closes_circuit(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, counter resets; need 5 more failures to open
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_reset_forces_closed(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_status_tracks_totals(self) -> None:
        cb = CircuitBreaker("test")
        cb.record_success()
        cb.record_failure()
        cb.record_success()
        status = cb.get_status()
        assert status.total_requests == 3
        assert status.total_failures == 1


# --- Unit tests: ConnectorRegistry ---

class TestConnectorRegistry:
    def test_get_creates_circuit_breaker(self) -> None:
        registry = ConnectorRegistry()
        cb = registry.get_circuit_breaker("tenant-1", "conn-1")
        assert cb.state == CircuitState.CLOSED

    def test_same_key_returns_same_breaker(self) -> None:
        registry = ConnectorRegistry()
        cb1 = registry.get_circuit_breaker("tenant-1", "conn-1")
        cb1.record_failure()
        cb2 = registry.get_circuit_breaker("tenant-1", "conn-1")
        assert cb2.get_status().failure_count == 1

    def test_list_breakers_by_tenant(self) -> None:
        registry = ConnectorRegistry()
        registry.get_circuit_breaker("tenant-1", "conn-a")
        registry.get_circuit_breaker("tenant-1", "conn-b")
        registry.get_circuit_breaker("tenant-2", "conn-c")
        breakers = registry.list_circuit_breakers("tenant-1")
        assert len(breakers) == 2
        assert "conn-a" in breakers
        assert "conn-b" in breakers

    def test_reset_circuit_breaker(self) -> None:
        registry = ConnectorRegistry()
        cb = registry.get_circuit_breaker("tenant-1", "conn-1")
        cb.record_failure()
        cb.record_failure()
        registry.reset_circuit_breaker("tenant-1", "conn-1")
        assert cb.state == CircuitState.CLOSED


# --- Unit tests: OAuthVault ---

class TestOAuthVault:
    def test_store_and_retrieve(self) -> None:
        vault = OAuthVault()
        vault.store("tenant-1", "conn-1", "oauth2", "refresh_token_abc")
        result = vault.retrieve("tenant-1", "conn-1")
        assert result == "refresh_token_abc"

    def test_retrieve_nonexistent_returns_none(self) -> None:
        vault = OAuthVault()
        assert vault.retrieve("tenant-1", "nonexistent") is None

    def test_delete_credential(self) -> None:
        vault = OAuthVault()
        vault.store("tenant-1", "conn-1", "api_key", "sk-123")
        assert vault.delete("tenant-1", "conn-1") is True
        assert vault.retrieve("tenant-1", "conn-1") is None

    def test_expired_credential_returns_none(self) -> None:
        vault = OAuthVault()
        vault.store("tenant-1", "conn-1", "oauth2", "token", expires_in_seconds=-1)
        assert vault.retrieve("tenant-1", "conn-1") is None

    def test_needs_refresh_within_buffer(self) -> None:
        vault = OAuthVault()
        vault.store("tenant-1", "conn-1", "oauth2", "token", expires_in_seconds=200)
        assert vault.needs_refresh("tenant-1", "conn-1", buffer_seconds=300) is True

    def test_no_refresh_needed_with_time_remaining(self) -> None:
        vault = OAuthVault()
        vault.store("tenant-1", "conn-1", "oauth2", "token", expires_in_seconds=3600)
        assert vault.needs_refresh("tenant-1", "conn-1", buffer_seconds=300) is False


# --- API endpoint tests ---

async def _signup_and_get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Conn User",
        "tenant_name": "Conn Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_create_connector(client: AsyncClient) -> None:
    """Create a connector and verify response."""
    token = await _signup_and_get_token(client, "conn1@test.com", "conn-1")
    resp = await client.post("/api/v1/connectors", headers={"Authorization": f"Bearer {token}"}, json={
        "name": "Salesforce Prod", "adapter_type": "salesforce", "auth_type": "oauth2",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Salesforce Prod"
    assert data["adapter_type"] == "salesforce"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_connectors_with_circuit_breaker(client: AsyncClient) -> None:
    """List connectors includes circuit breaker status."""
    token = await _signup_and_get_token(client, "conn2@test.com", "conn-2")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/connectors", headers=headers, json={
        "name": "Slack", "adapter_type": "slack",
    })
    resp = await client.get("/api/v1/connectors", headers=headers)
    assert resp.status_code == 200
    connectors = resp.json()["data"]
    assert len(connectors) >= 1
    assert connectors[0]["circuit_breaker"]["state"] == "closed"


@pytest.mark.asyncio
async def test_test_connector(client: AsyncClient) -> None:
    """Test connector returns health status."""
    token = await _signup_and_get_token(client, "conn3@test.com", "conn-3")
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post("/api/v1/connectors", headers=headers, json={
        "name": "HubSpot", "adapter_type": "hubspot",
    })
    connector_id = create_resp.json()["data"]["id"]
    test_resp = await client.post(f"/api/v1/connectors/{connector_id}/test", headers=headers)
    assert test_resp.status_code == 200
    assert test_resp.json()["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_delete_connector(client: AsyncClient) -> None:
    """Delete a connector removes it from list."""
    token = await _signup_and_get_token(client, "conn4@test.com", "conn-4")
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post("/api/v1/connectors", headers=headers, json={
        "name": "Temp", "adapter_type": "test",
    })
    connector_id = create_resp.json()["data"]["id"]
    del_resp = await client.delete(f"/api/v1/connectors/{connector_id}", headers=headers)
    assert del_resp.status_code == 200
    list_resp = await client.get("/api/v1/connectors", headers=headers)
    assert len(list_resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_cross_tenant_connector_isolation(client: AsyncClient) -> None:
    """Tenant B cannot see or test Tenant A's connectors."""
    token_a = await _signup_and_get_token(client, "a-conn@test.com", "a-conn")
    token_b = await _signup_and_get_token(client, "b-conn@test.com", "b-conn")

    await client.post("/api/v1/connectors", headers={"Authorization": f"Bearer {token_a}"}, json={
        "name": "A Secret SF", "adapter_type": "salesforce",
    })
    list_resp = await client.get("/api/v1/connectors", headers={"Authorization": f"Bearer {token_b}"})
    for c in list_resp.json()["data"]:
        assert c["name"] != "A Secret SF"
