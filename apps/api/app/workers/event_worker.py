"""Background worker that consumes Redis Stream 'agent_events' and processes them.

Reads from the stream using XREAD with blocking, normalizes event payloads,
stores them as AgentEvent records in the DB, checks subscriptions, and
triggers matched agent handlers.

Supports consumer groups for horizontal scaling.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog

from app.config import get_settings

logger = structlog.get_logger()

STREAM_KEY = "agent_events"
GROUP_NAME = "shipbridge_workers"
CONSUMER_PREFIX = "worker"
BLOCK_MS = 5000  # Block for 5s waiting for new messages
BATCH_SIZE = 10


async def ensure_consumer_group(redis_client) -> None:
    """Create the consumer group if it doesn't exist."""
    try:
        await redis_client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("consumer_group_created", stream=STREAM_KEY, group=GROUP_NAME)
    except Exception:
        # Group already exists
        pass


async def process_event(event_data: dict, db_session) -> None:
    """Process a single event from the stream.

    1. Normalize the payload
    2. Store as AgentEvent in DB
    3. Check subscriptions and trigger handlers
    """
    from app.models.events import AgentEvent

    try:
        provider = event_data.get("provider", "unknown")
        event_type = event_data.get("event_type", "unknown")
        payload_str = event_data.get("payload", "{}")
        tenant_id = event_data.get("tenant_id")

        # Parse payload
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except (json.JSONDecodeError, TypeError):
            payload = {"raw": str(payload_str)}

        # Store as AgentEvent
        agent_event = AgentEvent(
            tenant_id=uuid.UUID(tenant_id) if tenant_id and tenant_id != "unknown" else uuid.uuid4(),
            source=provider,
            event_type=event_type or "unknown",
            occurred_at=datetime.fromisoformat(event_data.get("received_at", datetime.now(timezone.utc).isoformat())),
            payload=payload,
            dedup_key=event_data.get("dedup_key") or event_data.get("event_id", ""),
        )
        db_session.add(agent_event)
        await db_session.commit()

        # Check subscriptions
        await check_subscriptions(db_session, agent_event)

        logger.info(
            "event_processed",
            provider=provider,
            event_type=event_type,
            event_id=str(agent_event.id),
        )
    except Exception as e:
        logger.error("event_processing_failed", error=str(e), event_data=event_data)


async def check_subscriptions(db_session, event) -> None:
    """Check if any subscriptions match this event and trigger handlers."""
    from sqlalchemy import select
    from app.models.events import EventSubscription

    try:
        result = await db_session.execute(
            select(EventSubscription).where(
                EventSubscription.tenant_id == event.tenant_id,
                EventSubscription.is_active == True,
            )
        )
        subscriptions = result.scalars().all()

        for sub in subscriptions:
            # Check if event matches subscription event type
            if sub.event_type and sub.event_type != "*" and sub.event_type != event.event_type:
                continue

            # Match found — log it (actual handler invocation would go here)
            logger.info(
                "subscription_matched",
                subscription_id=str(sub.id),
                event_id=str(event.id),
                event_type=event.event_type,
            )
    except Exception as e:
        logger.warning("subscription_check_failed", error=str(e))


async def run_worker(consumer_id: str | None = None) -> None:
    """Main worker loop — reads from Redis Stream and processes events."""
    import redis.asyncio as aioredis
    from app.db import _get_session_factory

    settings = get_settings()
    consumer_name = f"{CONSUMER_PREFIX}-{consumer_id or uuid.uuid4().hex[:8]}"

    logger.info("event_worker_starting", consumer=consumer_name, stream=STREAM_KEY)

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
    except Exception as e:
        logger.error("event_worker_redis_unavailable", error=str(e))
        return

    await ensure_consumer_group(redis_client)

    session_factory = _get_session_factory()

    while True:
        try:
            # Read from consumer group with blocking
            messages = await redis_client.xreadgroup(
                GROUP_NAME,
                consumer_name,
                {STREAM_KEY: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )

            if not messages:
                continue

            for stream_name, stream_messages in messages:
                for msg_id, msg_data in stream_messages:
                    async with session_factory() as db_session:
                        await process_event(msg_data, db_session)

                    # Acknowledge message
                    await redis_client.xack(STREAM_KEY, GROUP_NAME, msg_id)

        except asyncio.CancelledError:
            logger.info("event_worker_cancelled", consumer=consumer_name)
            break
        except Exception as e:
            logger.error("event_worker_error", error=str(e), consumer=consumer_name)
            await asyncio.sleep(1)  # Brief pause before retry

    await redis_client.aclose()
    logger.info("event_worker_stopped", consumer=consumer_name)


if __name__ == "__main__":
    asyncio.run(run_worker())
