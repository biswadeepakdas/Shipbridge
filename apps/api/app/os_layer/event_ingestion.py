"""Event ingestion pipeline — receives webhooks, deduplicates, normalizes, queues.

Flow:
1. Webhook arrives at /webhooks/{provider}
2. HMAC signature verified
3. 200 ACK returned immediately (< 200ms)
4. Deduplication check (dedup_key)
5. Normalization via RuleRegistry → JMESPath
6. If no rule → UnknownEventQueue
7. If processing fails after retries → Dead Letter Queue
"""

import hashlib
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

import structlog

from app.os_layer.dead_letter_queue import dead_letter_queue
from app.os_layer.dedup import dedup_engine
from app.os_layer.normalizer import NormalizationResult, normalize_event

logger = structlog.get_logger()

MAX_RETRIES = 10


class IngestedEvent(BaseModel):
    """Result of processing an inbound webhook event."""

    event_id: str
    provider: str
    dedup_key: str
    status: str  # "processed", "duplicate", "queued_unknown", "dead_lettered", "error"
    normalized_event_type: str | None = None
    message: str


def generate_dedup_key(provider: str, payload: dict) -> str:
    """Generate a dedup key from provider + payload content hash."""
    # Use provider + any id field + payload hash for uniqueness
    event_id = payload.get("id", payload.get("event_id", ""))
    if event_id:
        return f"{provider}:{event_id}"
    # Fallback: hash the full payload
    payload_hash = hashlib.sha256(str(sorted(payload.items())).encode()).hexdigest()[:12]
    return f"{provider}:{payload_hash}"


def ingest_webhook_event(
    provider: str,
    payload: dict,
    tenant_id: str | None = None,
    dedup_key: str | None = None,
) -> IngestedEvent:
    """Process an inbound webhook event through the full ingestion pipeline.

    Returns immediately with status. In production, heavy processing
    would be queued to Redis Streams.
    """
    event_id = str(uuid.uuid4())

    if not dedup_key:
        dedup_key = generate_dedup_key(provider, payload)

    # Step 1: Deduplication check
    if dedup_engine.is_duplicate(dedup_key):
        return IngestedEvent(
            event_id=event_id,
            provider=provider,
            dedup_key=dedup_key,
            status="duplicate",
            message="Event already processed (dedup collision)",
        )

    # Step 2: Extract trigger info
    trigger = payload.get("trigger", payload.get("event_type", payload.get("type", "unknown")))
    app = payload.get("app", payload.get("source", provider))

    # Step 3: Normalize via rule pipeline
    try:
        result: NormalizationResult = normalize_event(
            app=app,
            trigger=trigger,
            raw_payload=payload,
            tenant_id=tenant_id,
        )

        if result.success and result.normalized:
            logger.info("webhook_event_processed", provider=provider, dedup_key=dedup_key,
                       event_type=result.normalized.event_type)
            return IngestedEvent(
                event_id=event_id,
                provider=provider,
                dedup_key=dedup_key,
                status="processed",
                normalized_event_type=result.normalized.event_type,
                message="Event normalized successfully",
            )

        if result.queued_as_unknown:
            return IngestedEvent(
                event_id=event_id,
                provider=provider,
                dedup_key=dedup_key,
                status="queued_unknown",
                message=f"No rule for {app}:{trigger} — queued for rule generation",
            )

        # Normalization error
        return IngestedEvent(
            event_id=event_id,
            provider=provider,
            dedup_key=dedup_key,
            status="error",
            message=result.error or "Normalization failed",
        )

    except Exception as e:
        # Processing failure → DLQ
        dead_letter_queue.add(
            event_id=event_id,
            source=provider,
            event_type=trigger,
            payload=payload,
            failure_reason=str(e),
            retry_count=0,
            first_received_at=datetime.now(timezone.utc).isoformat(),
        )
        return IngestedEvent(
            event_id=event_id,
            provider=provider,
            dedup_key=dedup_key,
            status="dead_lettered",
            message=f"Processing failed: {e}",
        )
