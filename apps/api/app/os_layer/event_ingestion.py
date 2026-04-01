"""Event ingestion pipeline — receives webhooks, deduplicates, normalizes, queues via Redis Streams.

Flow:
1. Webhook arrives at /webhooks/{provider}
2. HMAC signature verified
3. 200 ACK returned immediately (< 200ms)
4. Event pushed to Redis Stream 'agent_events'
5. Background worker processes the stream
"""

import hashlib
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
import structlog
from redis.asyncio import Redis

from app.config import get_settings

logger = structlog.get_logger()

class IngestedEvent(BaseModel):
    """Result of pushing an inbound webhook event to the stream."""
    event_id: str
    provider: str
    dedup_key: str
    status: str  # "queued", "duplicate", "error"
    message: str

class EventIngestionSubsystem:
    """
    Production-ready event ingestion using Redis Streams.
    Ensures < 200ms ACK by offloading processing to background workers.
    """

    def __init__(self, redis: Redis):
        self.redis = redis
        self.stream_name = "agent_events"
        self.dedup_prefix = "event:dedup:"
        self.dedup_ttl = 86400 # 24h

    def generate_dedup_key(self, provider: str, payload: dict) -> str:
        """Generate a dedup key from provider + payload content hash."""
        event_id = payload.get("id", payload.get("event_id", ""))
        if event_id:
            return f"{provider}:{event_id}"
        payload_hash = hashlib.sha256(str(sorted(payload.items())).encode()).hexdigest()[:12]
        return f"{provider}:{payload_hash}"

    async def ingest_webhook_event(
        self,
        provider: str,
        payload: dict,
        tenant_id: Optional[str] = None,
    ) -> IngestedEvent:
        """
        Push an inbound webhook event to the Redis Stream.
        Returns immediately to guarantee < 200ms ACK.
        """
        event_id = str(uuid.uuid4())
        dedup_key = self.generate_dedup_key(provider, payload)
        dedup_redis_key = f"{self.dedup_prefix}{dedup_key}"

        # 1. Deduplication check (Atomic SETNX)
        is_new = await self.redis.set(dedup_redis_key, event_id, nx=True, ex=self.dedup_ttl)
        if not is_new:
            return IngestedEvent(
                event_id=event_id,
                provider=provider,
                dedup_key=dedup_key,
                status="duplicate",
                message="Event already processed (dedup collision)"
            )

        # 2. Push to Redis Stream
        event_data = {
            "event_id": event_id,
            "provider": provider,
            "tenant_id": tenant_id or "unknown",
            "payload": json.dumps(payload),
            "received_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            await self.redis.xadd(self.stream_name, event_data)
            return IngestedEvent(
                event_id=event_id,
                provider=provider,
                dedup_key=dedup_key,
                status="queued",
                message="Event queued for processing"
            )
        except Exception as e:
            logger.error("event_ingestion_failed", error=str(e), event_id=event_id)
            # Cleanup dedup key on failure so it can be retried
            await self.redis.delete(dedup_redis_key)
            return IngestedEvent(
                event_id=event_id,
                provider=provider,
                dedup_key=dedup_key,
                status="error",
                message=f"Failed to queue event: {str(e)}"
            )
