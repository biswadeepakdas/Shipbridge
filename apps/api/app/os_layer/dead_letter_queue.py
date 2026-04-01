"""Dead Letter Queue — stores events that exhausted retries."""

from datetime import datetime, timezone

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class DeadLetterEntry(BaseModel):
    """An event that failed processing after max retries."""

    id: str
    source: str
    event_type: str
    payload: dict
    failure_reason: str
    retry_count: int
    first_received_at: str
    dead_lettered_at: str


class DeadLetterQueue:
    """In-memory DLQ. Production uses a DB table for persistence."""

    def __init__(self) -> None:
        self._entries: list[DeadLetterEntry] = []

    def add(
        self,
        event_id: str,
        source: str,
        event_type: str,
        payload: dict,
        failure_reason: str,
        retry_count: int,
        first_received_at: str,
    ) -> DeadLetterEntry:
        """Add a failed event to the DLQ."""
        entry = DeadLetterEntry(
            id=event_id,
            source=source,
            event_type=event_type,
            payload=payload,
            failure_reason=failure_reason,
            retry_count=retry_count,
            first_received_at=first_received_at,
            dead_lettered_at=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(entry)
        logger.warning("event_dead_lettered", event_id=event_id, source=source,
                       reason=failure_reason, retries=retry_count)
        return entry

    def list_entries(self, limit: int = 50) -> list[DeadLetterEntry]:
        """List DLQ entries, newest first."""
        return list(reversed(self._entries[-limit:]))

    @property
    def size(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()


# Singleton
dead_letter_queue = DeadLetterQueue()
