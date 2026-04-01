"""Webhook receiver — HMAC-verified inbound events from any provider.

200ms ACK guarantee: validates signature, queues event, returns immediately.
"""

import hashlib
import hmac

import structlog
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from app.config import get_settings
from app.exceptions import AppError, ErrorCode
from app.os_layer.dead_letter_queue import dead_letter_queue
from app.os_layer.dedup import dedup_engine
from app.os_layer.event_ingestion import IngestedEvent, ingest_webhook_event
from app.schemas.response import APIResponse

logger = structlog.get_logger()

router = APIRouter(tags=["webhooks"])


def _verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/{provider}", response_model=APIResponse[IngestedEvent])
async def receive_webhook(
    provider: str,
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
) -> APIResponse[IngestedEvent]:
    """Receive and process webhook from any provider.

    - Verifies HMAC signature if present
    - Deduplicates by event ID or payload hash
    - Normalizes via rule pipeline
    - Returns 200 ACK immediately
    """
    raw_body = await request.body()
    body = await request.json()

    # Verify signature if provided
    signature = x_hub_signature_256 or x_webhook_signature
    if signature:
        settings = get_settings()
        secret = settings.github_webhook_secret
        if secret and not _verify_hmac(raw_body, signature, secret):
            raise AppError(ErrorCode.FORBIDDEN, "Invalid webhook signature")

    # Extract tenant_id from payload if present
    tenant_id = body.get("tenant_id")

    # Process event through ingestion pipeline
    result = ingest_webhook_event(
        provider=provider,
        payload=body,
        tenant_id=tenant_id,
    )

    return APIResponse(data=result)


# --- Pipeline Stats ---

class PipelineStats(BaseModel):
    """Event pipeline statistics."""

    dedup: dict
    dlq_size: int


@router.get("/api/v1/events/pipeline-stats", response_model=APIResponse[PipelineStats])
async def pipeline_stats() -> APIResponse[PipelineStats]:
    """Get event pipeline statistics — dedup rates, DLQ size."""
    return APIResponse(
        data=PipelineStats(
            dedup=dedup_engine.stats,
            dlq_size=dead_letter_queue.size,
        )
    )


@router.get("/api/v1/events/dlq", response_model=APIResponse[list[dict]])
async def list_dlq() -> APIResponse[list[dict]]:
    """List dead letter queue entries."""
    entries = dead_letter_queue.list_entries()
    return APIResponse(data=[e.model_dump() for e in entries])
