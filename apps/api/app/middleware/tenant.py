"""Tenant context middleware — extracts tenant_id from JWT auth context."""

from fastapi import Depends, Request

from app.middleware.auth import AuthContext, get_auth_context


async def get_tenant_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    """Extract tenant_id from authenticated request context."""
    return auth.tenant_id
