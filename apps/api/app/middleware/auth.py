"""JWT authentication middleware — extracts tenant_id and user info from token or API key."""

from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.services.auth import JWTError, UserInfo, decode_access_token, verify_api_key


@dataclass
class AuthContext:
    """Authenticated request context with user and tenant info."""

    user_id: str
    tenant_id: str
    role: str


async def get_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Extract auth context from JWT Bearer token or API key header.

    Checks X-API-Key header first, then Authorization: Bearer <token>.
    """
    # API Key auth
    if x_api_key:
        api_key = await verify_api_key(db, x_api_key)
        if not api_key:
            raise AppError(ErrorCode.UNAUTHORIZED, "Invalid API key")
        return AuthContext(
            user_id=str(api_key.created_by or ""),
            tenant_id=str(api_key.tenant_id),
            role=api_key.scope,
        )

    # JWT Bearer auth
    if not authorization:
        raise AppError(ErrorCode.UNAUTHORIZED, "Missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(ErrorCode.UNAUTHORIZED, "Invalid authorization scheme — use Bearer <token>")

    try:
        payload = decode_access_token(token)
    except (JWTError, KeyError) as e:
        raise AppError(ErrorCode.UNAUTHORIZED, f"Invalid or expired token: {e}")

    return AuthContext(
        user_id=payload.sub,
        tenant_id=payload.tenant_id,
        role=payload.role,
    )


async def get_tenant_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    """Convenience dependency — returns just the tenant_id string."""
    return auth.tenant_id
