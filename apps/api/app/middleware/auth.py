"""JWT authentication middleware — stub for Day 1, implemented on Day 2."""

from dataclasses import dataclass


@dataclass
class Tenant:
    """Tenant context extracted from JWT."""

    id: str
    name: str = "dev-tenant"


async def get_tenant() -> Tenant:
    """FastAPI dependency — returns mock tenant for Day 1 development."""
    return Tenant(id="dev-tenant-001")


async def get_current_user() -> dict:
    """FastAPI dependency — returns mock user for Day 1 development."""
    return {"user_id": "dev-user-001", "tenant_id": "dev-tenant-001", "role": "admin"}
