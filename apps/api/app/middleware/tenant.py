"""Tenant context injection middleware — stub for Day 1, implemented on Day 2."""


async def get_tenant_context() -> dict:
    """FastAPI dependency — returns mock tenant context for Day 1."""
    return {"tenant_id": "dev-tenant-001"}
