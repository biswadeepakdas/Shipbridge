"""Webhook receiver — HMAC-verified inbound events from any provider.

200ms ACK guarantee: validates signature, queues event to Redis Stream, returns immediately.
"""

import hashlib
import hmac
import structlog
from fastapi import APIRouter, Header, Request, Depends
from redis.asyncio import Redis, from_url

from app.config import get_settings
from app.exceptions import AppError, ErrorCode
from app.os_layer.event_ingestion import IngestedEvent, EventIngestionSubsystem
from app.schemas.response import APIResponse

logger = structlog.get_logger()

router = APIRouter(tags=["webhooks"])

async def get_redis(request: Request) -> Redis:
    """FastAPI dependency for Redis — uses pooled connection from app state."""
    if hasattr(request.app.state, "redis") and request.app.state.redis:
        return request.app.state.redis
    settings = get_settings()
    return from_url(settings.redis_url, decode_responses=True)

def _verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@router.post("/webhooks/{provider}", response_model=APIResponse[IngestedEvent])
async def receive_webhook(
    provider: str,
    request: Request,
    redis: Redis = Depends(get_redis),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
) -> APIResponse[IngestedEvent]:
    """Receive and process webhook from any provider.

    - Verifies HMAC signature if present
    - Deduplicates by event ID or payload hash
    - Pushes to Redis Stream for async processing
    - Returns 200 ACK immediately (< 200ms)
    """
    raw_body = await request.body()
    body = await request.json()

    # Verify signature
    signature = x_hub_signature_256 or x_webhook_signature
    settings = get_settings()
    provider_secrets = {
        "github": settings.github_webhook_secret,
    }
    secret = provider_secrets.get(provider, "")

    if secret:
        # Provider has a configured secret — signature is mandatory
        if not signature:
            raise AppError(ErrorCode.FORBIDDEN, "Missing webhook signature header")
        if not _verify_hmac(raw_body, signature, secret):
            raise AppError(ErrorCode.FORBIDDEN, "Invalid webhook signature")
    elif signature:
        # Signature provided but no secret configured — cannot verify, reject
        logger.warning("webhook_secret_missing", provider=provider)
        raise AppError(ErrorCode.FORBIDDEN, f"No webhook secret configured for provider '{provider}'")
    else:
        # No secret and no signature — only allow in development
        if settings.environment not in ("development", "test"):
            logger.warning("webhook_unsigned_rejected", provider=provider)
            raise AppError(ErrorCode.FORBIDDEN, "Unsigned webhooks are not accepted in production")

    # Extract tenant_id from payload if present
    tenant_id = body.get("tenant_id")

    # Process event through ingestion pipeline (Redis Streams)
    subsystem = EventIngestionSubsystem(redis)
    result = await subsystem.ingest_webhook_event(
        provider=provider,
        payload=body,
        tenant_id=tenant_id,
    )

    return APIResponse(data=result)
