"""Auth routes — token exchange, API key management, signup/signin."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.schemas.response import APIResponse
from app.services.auth import (
    APIKeyResponse,
    TokenPair,
    create_access_token,
    create_api_key,
    create_tenant_with_owner,
    get_or_create_user,
    get_user_membership,
    list_api_keys,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# --- Request/Response Schemas ---

class ExchangeRequest(BaseModel):
    """Swap a Supabase JWT for an internal session token."""

    email: str
    full_name: str
    supabase_uid: str | None = None
    tenant_id: str | None = None


class SignupRequest(BaseModel):
    """Register a new user and create their tenant."""

    email: str
    full_name: str
    tenant_name: str
    tenant_slug: str
    supabase_uid: str | None = None


class SignupResponse(BaseModel):
    """Signup result with user, tenant, and token."""

    user_id: str
    tenant_id: str
    token: TokenPair


class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str
    scope: str = "read"


# --- Routes ---

@router.post("/signup", response_model=APIResponse[SignupResponse])
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)) -> APIResponse[SignupResponse]:
    """Register a new user and create their first tenant."""
    user = await get_or_create_user(db, body.email, body.full_name, body.supabase_uid)
    tenant = await create_tenant_with_owner(db, body.tenant_name, body.tenant_slug, user)
    await db.commit()

    token = create_access_token(str(user.id), str(tenant.id), "owner")
    return APIResponse(
        data=SignupResponse(user_id=str(user.id), tenant_id=str(tenant.id), token=token)
    )


@router.post("/exchange", response_model=APIResponse[TokenPair])
async def exchange_token(
    body: ExchangeRequest, db: AsyncSession = Depends(get_db)
) -> APIResponse[TokenPair]:
    """Exchange a Supabase JWT for an internal ShipBridge session token."""
    user = await get_or_create_user(db, body.email, body.full_name, body.supabase_uid)

    if body.tenant_id:
        membership = await get_user_membership(db, user.id, uuid.UUID(body.tenant_id))
        if not membership:
            raise AppError(ErrorCode.FORBIDDEN, "User is not a member of this tenant")
        tenant_id = body.tenant_id
        role = membership.role
    else:
        # Default to first tenant membership
        if not user.memberships:
            raise AppError(ErrorCode.NOT_FOUND, "User has no tenant memberships — sign up first")
        membership = user.memberships[0]
        tenant_id = str(membership.tenant_id)
        role = membership.role

    await db.commit()
    token = create_access_token(str(user.id), tenant_id, role)
    return APIResponse(data=token)


@router.post("/api-keys", response_model=APIResponse[APIKeyResponse])
async def create_key(
    body: CreateAPIKeyRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[APIKeyResponse]:
    """Create a new API key for the authenticated tenant."""
    if body.scope not in ("read", "write", "admin"):
        raise AppError(ErrorCode.VALIDATION, "Scope must be read, write, or admin")

    if auth.role not in ("admin", "owner"):
        raise AppError(ErrorCode.FORBIDDEN, "Only admins and owners can create API keys")

    api_key, raw_key = await create_api_key(
        db,
        tenant_id=uuid.UUID(auth.tenant_id),
        name=body.name,
        scope=body.scope,
        created_by=uuid.UUID(auth.user_id) if auth.user_id else None,
    )
    await db.commit()

    return APIResponse(
        data=APIKeyResponse(
            id=str(api_key.id),
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            scope=api_key.scope,
            created_at=api_key.created_at.isoformat(),
            raw_key=raw_key,
        )
    )


@router.get("/api-keys", response_model=APIResponse[list[APIKeyResponse]])
async def list_keys(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[APIKeyResponse]]:
    """List all active API keys for the authenticated tenant."""
    keys = await list_api_keys(db, uuid.UUID(auth.tenant_id))
    return APIResponse(
        data=[
            APIKeyResponse(
                id=str(k.id),
                name=k.name,
                key_prefix=k.key_prefix,
                scope=k.scope,
                created_at=k.created_at.isoformat(),
            )
            for k in keys
        ]
    )
