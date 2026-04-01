"""UnknownEventQueue — stores unrecognized triggers for offline rule generation.

Events with no matching NormalizationRule are queued here. The RuleGeneratorJob
(Day 16) drains this queue and generates draft rules via LLM.
"""

from datetime import datetime, timezone

from pydantic import BaseModel


class UnknownEvent(BaseModel):
    """An event that arrived with no matching normalization rule."""

    id: str
    app: str
    trigger: str
    raw_payload: dict
    received_at: str
    tenant_id: str | None = None


class UnknownEventQueue:
    """In-memory queue for unknown events. Production uses Redis list or DB table."""

    def __init__(self) -> None:
        self._queue: list[UnknownEvent] = []

    def enqueue(self, event: UnknownEvent) -> None:
        """Add an unknown event to the queue."""
        self._queue.append(event)

    def drain(self, limit: int = 50) -> list[UnknownEvent]:
        """Drain up to `limit` events from the queue. Returns and removes them."""
        batch = self._queue[:limit]
        self._queue = self._queue[limit:]
        return batch

    def peek(self, limit: int = 10) -> list[UnknownEvent]:
        """Peek at events without removing them."""
        return self._queue[:limit]

    @property
    def size(self) -> int:
        """Current queue depth."""
        return len(self._queue)

    def clear(self) -> None:
        """Clear the queue."""
        self._queue.clear()


# Singleton
unknown_event_queue = UnknownEventQueue()
