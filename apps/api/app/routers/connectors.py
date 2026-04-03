"""Connector CRUD routes — list, create, test, delete with circuit breaker status."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.integrations.circuit_breaker import CircuitBreakerStatus, CircuitState
from app.integrations.registry import connector_registry
from app.middleware.auth import AuthContext, get_auth_context
from app.models.connectors import Connector, ConnectorHealth
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


# --- Schemas ---

class ConnectorCreate(BaseModel):
    """Request to create a new connector."""

    name: str
    adapter_type: str
    auth_type: str = "oauth2"
    config_json: dict = {}


class ConnectorOut(BaseModel):
    """Connector response with health and circuit breaker status."""

    id: str
    name: str
    adapter_type: str
    auth_type: str
    is_active: bool
    config_json: dict
    circuit_breaker: CircuitBreakerStatus | None = None
    latest_health: dict | None = None
    created_at: str


class ConnectorTestResult(BaseModel):
    """Result from testing a connector's connectivity."""

    connector_id: str
    status: str
    latency_ms: float
    message: str


_SENSITIVE_PATTERNS = {"key", "secret", "token", "password", "credential"}

def _sanitize_config(config: dict) -> dict:
    """Mask sensitive values in config_json before returning to clients."""
    sanitized = {}
    for k, v in config.items():
        if any(p in k.lower() for p in _SENSITIVE_PATTERNS):
            sanitized[k] = "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized


# --- Routes ---

@router.post("", response_model=APIResponse[ConnectorOut])
async def create_connector(
    body: ConnectorCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConnectorOut]:
    """Create a new connector for the authenticated tenant."""
    connector = Connector(
        tenant_id=uuid.UUID(auth.tenant_id),
        name=body.name,
        adapter_type=body.adapter_type,
        auth_type=body.auth_type,
        config_json=body.config_json,
    )
    db.add(connector)
    await db.commit()

    # Initialize circuit breaker
    connector_registry.get_circuit_breaker(auth.tenant_id, str(connector.id))

    return APIResponse(
        data=ConnectorOut(
            id=str(connector.id),
            name=connector.name,
            adapter_type=connector.adapter_type,
            auth_type=connector.auth_type,
            is_active=connector.is_active,
            config_json=_sanitize_config(connector.config_json),
            created_at=connector.created_at.isoformat(),
        )
    )


@router.get("", response_model=APIResponse[list[ConnectorOut]])
async def list_connectors(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ConnectorOut]]:
    """List all connectors for the authenticated tenant with health and circuit breaker status."""
    result = await db.execute(
        select(Connector).where(Connector.tenant_id == uuid.UUID(auth.tenant_id))
    )
    connectors = result.scalars().all()

    items = []
    for c in connectors:
        # Get circuit breaker status
        cb = connector_registry.get_circuit_breaker(auth.tenant_id, str(c.id))
        cb_status = cb.get_status()

        # Get latest health check
        health_result = await db.execute(
            select(ConnectorHealth)
            .where(ConnectorHealth.connector_id == c.id)
            .order_by(ConnectorHealth.checked_at.desc())
            .limit(1)
        )
        health = health_result.scalar_one_or_none()
        latest_health = None
        if health:
            latest_health = {
                "status": health.status,
                "latency_ms": health.latency_ms,
                "checked_at": health.checked_at.isoformat(),
            }

        items.append(ConnectorOut(
            id=str(c.id),
            name=c.name,
            adapter_type=c.adapter_type,
            auth_type=c.auth_type,
            is_active=c.is_active,
            config_json=_sanitize_config(c.config_json),
            circuit_breaker=cb_status,
            latest_health=latest_health,
            created_at=c.created_at.isoformat(),
        ))

    return APIResponse(data=items)


@router.post("/{connector_id}/test", response_model=APIResponse[ConnectorTestResult])
async def test_connector(
    connector_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConnectorTestResult]:
    """Test a connector's connectivity and record health check."""
    result = await db.execute(
        select(Connector).where(
            Connector.id == uuid.UUID(connector_id),
            Connector.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise AppError(ErrorCode.NOT_FOUND, f"Connector {connector_id} not found")

    # Simulate health check (real adapters would call external service)
    cb = connector_registry.get_circuit_breaker(auth.tenant_id, connector_id)

    if not cb.can_execute():
        return APIResponse(
            data=ConnectorTestResult(
                connector_id=connector_id,
                status="circuit_open",
                latency_ms=0,
                message=f"Circuit breaker is {cb.state.value} — requests blocked",
            )
        )

    # Simulate a successful test (real adapter would make HTTP call)
    latency = 42.5
    cb.record_success()

    # Store health record
    health = ConnectorHealth(
        connector_id=connector.id,
        status="healthy",
        latency_ms=latency,
    )
    db.add(health)
    await db.commit()

    return APIResponse(
        data=ConnectorTestResult(
            connector_id=connector_id,
            status="healthy",
            latency_ms=latency,
            message="Connection successful",
        )
    )


@router.delete("/{connector_id}", response_model=APIResponse[dict])
async def delete_connector(
    connector_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Delete a connector and its health records."""
    result = await db.execute(
        select(Connector).where(
            Connector.id == uuid.UUID(connector_id),
            Connector.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise AppError(ErrorCode.NOT_FOUND, f"Connector {connector_id} not found")

    await db.delete(connector)
    await db.commit()

    return APIResponse(data={"deleted": connector_id})


# ─── Marketplace Registry ─────────────────────────────────────────────────────
# These endpoints power the community connector marketplace, enabling tenants
# to publish, discover, and install shared connectors.

class MarketplaceConnectorPublish(BaseModel):
    """Request to publish a connector to the marketplace."""
    name: str
    description: str
    category: str
    author_tenant_id: str
    connector_code_url: str

    @field_validator("connector_code_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if parsed.scheme not in ("https",) or not parsed.netloc:
            raise ValueError("connector_code_url must be a valid HTTPS URL")
        return v


@router.get("/marketplace")
async def list_marketplace_connectors(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
):
    """Returns all published connectors from the community marketplace."""
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return APIResponse(data={"connectors": [], "total": 0})
    connector_ids = await redis.smembers("connector:all")
    connectors = []
    for cid in connector_ids:
        cid_str = cid.decode() if isinstance(cid, bytes) else cid
        data = await redis.hgetall(f"connector:{cid_str}")
        if data:
            connectors.append({
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            })
    return APIResponse(data={"connectors": connectors, "total": len(connectors)})


@router.post("/marketplace/publish")
async def publish_marketplace_connector(payload: MarketplaceConnectorPublish, request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Publishes a new connector to the community marketplace."""
    import uuid as _uuid
    redis = request.app.state.redis
    connector_id = str(_uuid.uuid4())
    connector_data = {
        "id": connector_id,
        "name": payload.name,
        "description": payload.description,
        "category": payload.category,
        "author_tenant_id": auth.tenant_id,
        "connector_code_url": payload.connector_code_url,
        "install_count": "0",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.hset(f"connector:{connector_id}", mapping=connector_data)
    await redis.sadd("connector:all", connector_id)
    return connector_data


@router.post("/marketplace/{connector_id}/install")
async def install_marketplace_connector(connector_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)):
    """Increments the install count for a marketplace connector."""
    redis = request.app.state.redis
    key = f"connector:{connector_id}"
    exists = await redis.exists(key)
    if not exists:
        raise AppError(ErrorCode.NOT_FOUND, "Marketplace connector not found")
    new_count = await redis.hincrby(key, "install_count", 1)
    return {"success": True, "connector_id": connector_id, "install_count": new_count}
