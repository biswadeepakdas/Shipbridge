import json
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel
from redis.asyncio import Redis

class UnknownEvent(BaseModel):
    """An event that arrived with no matching normalization rule."""
    id: str
    app: str
    trigger: str
    raw_payload: dict
    received_at: str
    tenant_id: str | None = None

class UnknownEventQueue:
    """Redis-backed queue for unknown events."""
    def __init__(self, redis: Redis):
        self.redis = redis
        self.queue_key = "unknown_events_queue"

    async def enqueue(self, event: UnknownEvent) -> None:
        """Add an unknown event to the Redis list."""
        await self.redis.lpush(self.queue_key, event.model_dump_json())

    async def drain(self, limit: int = 50) -> List[UnknownEvent]:
        """Drain up to `limit` events from the Redis list. Returns and removes them."""
        # Use LPOP to get elements from the left (head) of the list
        # We need to pop one by one as LPOP doesn't support count in older Redis versions
        # and to ensure proper deserialization.
        events: List[UnknownEvent] = []
        for _ in range(limit):
            item = await self.redis.rpop(self.queue_key) # rpop to get from tail, lpush adds to head
            if item:
                events.append(UnknownEvent.model_validate_json(item))
            else:
                break
        return events

    async def peek(self, limit: int = 10) -> List[UnknownEvent]:
        """Peek at events without removing them."""
        items = await self.redis.lrange(self.queue_key, 0, limit - 1)
        return [UnknownEvent.model_validate_json(item) for item in items]

    async def size(self) -> int:
        """Current queue depth."""
        return await self.redis.llen(self.queue_key)

    async def clear(self) -> None:
        """Clear the queue."""
        await self.redis.delete(self.queue_key)

# The singleton will now be instantiated with a Redis client in the FastAPI app's lifespan event
# For now, we remove the global singleton to avoid issues with direct imports
# unknown_event_queue = UnknownEventQueue()
