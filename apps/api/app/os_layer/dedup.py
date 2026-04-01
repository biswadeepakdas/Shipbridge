"""DeduplicationEngine — prevents duplicate agent triggers using dedup_key.

Uses SETNX-style semantics with 24h TTL. In production, backed by Redis.
"""

import time

import structlog

logger = structlog.get_logger()

# Default TTL: 24 hours
DEFAULT_TTL_SECONDS = 86400


class DeduplicationEngine:
    """In-memory deduplication engine. Production uses Redis SETNX with TTL."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}  # dedup_key → timestamp
        self._total_checked = 0
        self._total_duplicates = 0

    def is_duplicate(self, dedup_key: str) -> bool:
        """Check if a dedup_key has been seen within the TTL window.

        Returns True if duplicate (already seen), False if new.
        Also registers the key if new.
        """
        self._total_checked += 1
        self._cleanup_expired()

        if dedup_key in self._seen:
            self._total_duplicates += 1
            logger.debug("dedup_collision", key=dedup_key)
            return True

        self._seen[dedup_key] = time.time()
        return False

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, t in self._seen.items() if (now - t) > self.ttl_seconds]
        for k in expired:
            del self._seen[k]

    @property
    def stats(self) -> dict:
        return {
            "total_checked": self._total_checked,
            "total_duplicates": self._total_duplicates,
            "active_keys": len(self._seen),
            "dedup_rate": round(self._total_duplicates / max(self._total_checked, 1), 3),
        }

    def clear(self) -> None:
        self._seen.clear()
        self._total_checked = 0
        self._total_duplicates = 0


# Singleton
dedup_engine = DeduplicationEngine()
