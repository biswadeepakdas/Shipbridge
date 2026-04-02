"""Authentication service — JWT handling, API key management, user/tenant ops."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import base64
import json
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.auth import APIKey, Membership, Tenant, User


# --- Schemas ---

class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    tenant_id: str
    role: str
    exp: datetime


class TokenPair(BaseModel):
    """Access + refresh token pair."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""

    name: str
    scope: str = "read"


class APIKeyResponse(BaseModel):
    """API key response — raw key only returned on creation."""

    id: str
    name: str
    key_prefix: str
    scope: str
    created_at: str
    raw_key: str | None = None


class UserInfo(BaseModel):
    """User info from JWT or API key."""

    user_id: str
    tenant_id: str
    role: str


# --- JWT Operations (HMAC-SHA256, pure Python) ---


class JWTError(Exception):
    """JWT encoding/decoding error."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _jwt_encode(payload: dict, secret: str) -> str:
    """Encode a JWT with HMAC-SHA256."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(signature)}"


def _jwt_decode(token: str, secret: str) -> dict:
    """Decode and verify a JWT with HMAC-SHA256."""
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("Invalid token format")
    header_b64, body_b64, sig_b64 = parts
    expected_sig = hmac.new(secret.encode(), f"{header_b64}.{body_b64}".encode(), hashlib.sha256).digest()
    actual_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise JWTError("Invalid signature")
    payload = json.loads(_b64url_decode(body_b64))
    if "exp" in payload and datetime.fromtimestamp(payload["exp"], tz=timezone.utc) < datetime.now(timezone.utc):
        raise JWTError("Token expired")
    return payload


def create_access_token(user_id: str, tenant_id: str, role: str) -> TokenPair:
    """Create a signed JWT access token."""
    settings = get_settings()
    expires_delta = timedelta(hours=24)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    token = _jwt_encode(payload, settings.jwt_secret)
    return TokenPair(access_token=token, expires_in=int(expires_delta.total_seconds()))


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token."""
    settings = get_settings()
    payload = _jwt_decode(token, settings.jwt_secret)
    return TokenPayload(
        sub=payload["sub"],
        tenant_id=payload["tenant_id"],
        role=payload["role"],
        exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


# --- API Key Operations ---

def _hash_api_key(raw_key: str) -> str:
    """HMAC-SHA256 hash an API key using the app secret."""
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode(), raw_key.encode(), hashlib.sha256
    ).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (raw_key, key_prefix, key_hash)."""
    raw_key = f"sb_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:8]
    key_hash = _hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


async def create_api_key(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    scope: str,
    created_by: uuid.UUID | None = None,
) -> tuple[APIKey, str]:
    """Create and store a new API key. Returns (model, raw_key)."""
    raw_key, key_prefix, key_hash = generate_api_key()
    api_key = APIKey(
        tenant_id=tenant_id,
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scope=scope,
        created_by=created_by,
    )
    db.add(api_key)
    await db.flush()
    return api_key, raw_key


async def verify_api_key(db: AsyncSession, raw_key: str) -> APIKey | None:
    """Verify an API key by HMAC comparison. Returns the key record or None."""
    key_hash = _hash_api_key(raw_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key:
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.flush()
    return api_key


# --- Tenant & User Operations ---

async def get_or_create_user(
    db: AsyncSession, email: str, full_name: str, supabase_uid: str | None = None
) -> User:
    """Find existing user by email or create a new one."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(email=email, full_name=full_name, supabase_uid=supabase_uid)
    db.add(user)
    await db.flush()
    return user


async def create_tenant_with_owner(
    db: AsyncSession, tenant_name: str, tenant_slug: str, owner: User
) -> Tenant:
    """Create a new tenant and add the given user as owner."""
    tenant = Tenant(name=tenant_name, slug=tenant_slug)
    db.add(tenant)
    await db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=owner.id, role="owner")
    db.add(membership)
    await db.flush()
    return tenant


async def get_user_membership(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> Membership | None:
    """Get a user's membership in a specific tenant."""
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def list_api_keys(db: AsyncSession, tenant_id: uuid.UUID) -> list[APIKey]:
    """List all active API keys for a tenant."""
    result = await db.execute(
        select(APIKey).where(APIKey.tenant_id == tenant_id, APIKey.is_active.is_(True))
    )
    return list(result.scalars().all())
