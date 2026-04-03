"""OAuthVault — secure credential storage for connector tokens.

In production, uses Supabase Vault (AES-256). For local dev, uses
in-memory storage with basic obfuscation.
"""

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.config import get_settings


class StoredCredential(BaseModel):
    """Credential record stored in the vault."""

    id: str
    connector_id: str
    tenant_id: str
    credential_type: str  # "oauth2", "api_key", "basic"
    encrypted_data: str
    expires_at: str | None = None
    created_at: str
    updated_at: str


class OAuthVault:
    """In-memory credential vault. Production would use Supabase Vault AES-256."""

    def __init__(self) -> None:
        self._store: dict[str, StoredCredential] = {}

    def _vault_key(self, tenant_id: str, connector_id: str) -> str:
        return f"{tenant_id}:{connector_id}"

    def _encrypt(self, data: str) -> str:
        """Basic obfuscation for dev. Production uses AES-256 via Supabase Vault."""
        settings = get_settings()
        if settings.environment not in ("development", "test"):
            raise RuntimeError(
                "OAuthVault (in-memory, base64) must not be used outside development/test. "
                "Configure SupabaseVault for production by setting SUPABASE_SERVICE_KEY."
            )
        key = settings.jwt_secret.encode()
        signature = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()[:8]
        encoded = base64.b64encode(data.encode()).decode()
        return f"{signature}:{encoded}"

    def _decrypt(self, encrypted: str) -> str:
        """Reverse the basic obfuscation."""
        _, encoded = encrypted.split(":", 1)
        return base64.b64decode(encoded).decode()

    def store(
        self,
        tenant_id: str,
        connector_id: str,
        credential_type: str,
        data: str,
        expires_in_seconds: int | None = None,
    ) -> StoredCredential:
        """Store a credential in the vault."""
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_in_seconds:
            expires_at = (now + timedelta(seconds=expires_in_seconds)).isoformat()

        cred = StoredCredential(
            id=str(uuid.uuid4()),
            connector_id=connector_id,
            tenant_id=tenant_id,
            credential_type=credential_type,
            encrypted_data=self._encrypt(data),
            expires_at=expires_at,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        self._store[self._vault_key(tenant_id, connector_id)] = cred
        return cred

    def retrieve(self, tenant_id: str, connector_id: str) -> str | None:
        """Retrieve and decrypt a credential. Returns None if not found or expired."""
        key = self._vault_key(tenant_id, connector_id)
        cred = self._store.get(key)
        if not cred:
            return None

        if cred.expires_at:
            expires = datetime.fromisoformat(cred.expires_at)
            if expires < datetime.now(timezone.utc):
                return None

        return self._decrypt(cred.encrypted_data)

    def delete(self, tenant_id: str, connector_id: str) -> bool:
        """Delete a credential from the vault."""
        key = self._vault_key(tenant_id, connector_id)
        if key in self._store:
            del self._store[key]
            return True
        return False

    def needs_refresh(self, tenant_id: str, connector_id: str, buffer_seconds: int = 300) -> bool:
        """Check if a credential needs proactive refresh (within buffer of expiry)."""
        key = self._vault_key(tenant_id, connector_id)
        cred = self._store.get(key)
        if not cred or not cred.expires_at:
            return False
        expires = datetime.fromisoformat(cred.expires_at)
        return (expires - timedelta(seconds=buffer_seconds)) < datetime.now(timezone.utc)


class SupabaseVault:
    """Supabase Vault-backed credential storage (AES-256-GCM via pgsodium).

    Uses Supabase Vault SQL functions for real encryption at rest.
    Requires PostgreSQL with the vault extension enabled.
    """

    def __init__(self, session_factory: object) -> None:
        self._session_factory = session_factory

    def _secret_name(self, tenant_id: str, connector_id: str) -> str:
        return f"shipbridge:{tenant_id}:{connector_id}"

    async def store(
        self,
        tenant_id: str,
        connector_id: str,
        credential_type: str,
        data: str,
        expires_in_seconds: int | None = None,
    ) -> StoredCredential:
        """Store a credential in Supabase Vault (AES-256 encrypted)."""
        from sqlalchemy import text

        name = self._secret_name(tenant_id, connector_id)
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            await session.execute(
                text("SELECT vault.create_secret(:secret, :name, :description)"),
                {"secret": data, "name": name, "description": f"{credential_type}:{connector_id}"},
            )
            await session.commit()

        expires_at = None
        if expires_in_seconds:
            expires_at = (now + timedelta(seconds=expires_in_seconds)).isoformat()

        return StoredCredential(
            id=name,
            connector_id=connector_id,
            tenant_id=tenant_id,
            credential_type=credential_type,
            encrypted_data="[vault-encrypted]",
            expires_at=expires_at,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

    async def retrieve(self, tenant_id: str, connector_id: str) -> str | None:
        """Retrieve and decrypt a credential from Supabase Vault."""
        from sqlalchemy import text

        name = self._secret_name(tenant_id, connector_id)

        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = :name"),
                {"name": name},
            )
            row = result.first()
            return row[0] if row else None

    async def delete(self, tenant_id: str, connector_id: str) -> bool:
        """Delete a credential from Supabase Vault."""
        from sqlalchemy import text

        name = self._secret_name(tenant_id, connector_id)

        async with self._session_factory() as session:
            result = await session.execute(
                text("DELETE FROM vault.secrets WHERE name = :name"),
                {"name": name},
            )
            await session.commit()
            return result.rowcount > 0


def get_vault(use_supabase: bool = False, session_factory: object = None) -> OAuthVault | SupabaseVault:
    """Factory: returns SupabaseVault for production, OAuthVault for dev/test."""
    if use_supabase and session_factory:
        return SupabaseVault(session_factory)
    return OAuthVault()


# Singleton — in-memory for dev/test
oauth_vault = OAuthVault()
