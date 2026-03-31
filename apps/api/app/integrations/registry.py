"""ConnectorRegistry — lookup connectors by (tenant_id, name) with circuit breaker tracking."""

import uuid
from typing import Any

from app.integrations.circuit_breaker import CircuitBreaker


class ConnectorRegistry:
    """Registry for connector instances and their circuit breakers.

    In production, state would be backed by Redis with 1h TTL cache.
    """

    def __init__(self) -> None:
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _breaker_key(self, tenant_id: str, connector_id: str) -> str:
        """Generate unique key for a circuit breaker."""
        return f"{tenant_id}:{connector_id}"

    def get_circuit_breaker(self, tenant_id: str, connector_id: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a connector."""
        key = self._breaker_key(tenant_id, connector_id)
        if key not in self._circuit_breakers:
            self._circuit_breakers[key] = CircuitBreaker(name=key)
        return self._circuit_breakers[key]

    def list_circuit_breakers(self, tenant_id: str) -> dict[str, CircuitBreaker]:
        """List all circuit breakers for a tenant."""
        prefix = f"{tenant_id}:"
        return {
            k.removeprefix(prefix): v
            for k, v in self._circuit_breakers.items()
            if k.startswith(prefix)
        }

    def reset_circuit_breaker(self, tenant_id: str, connector_id: str) -> None:
        """Force-reset a circuit breaker to closed state."""
        key = self._breaker_key(tenant_id, connector_id)
        if key in self._circuit_breakers:
            self._circuit_breakers[key].reset()


# Singleton registry
connector_registry = ConnectorRegistry()
