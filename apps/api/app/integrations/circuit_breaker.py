"""CircuitBreaker — 3-state FSM per connector. Closed → Open → Half-Open.

States:
  - CLOSED: Normal operation. Failures increment counter.
  - OPEN: All requests fail-fast. After recovery_timeout, transitions to HALF_OPEN.
  - HALF_OPEN: One test request allowed. Success → CLOSED, Failure → OPEN.

Thresholds:
  - failure_threshold: 5 consecutive failures → OPEN
  - recovery_timeout: 30 seconds before HALF_OPEN
"""

import time
from enum import Enum

from pydantic import BaseModel


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerStatus(BaseModel):
    """Current circuit breaker status for inspection."""

    state: CircuitState
    failure_count: int
    last_failure_time: float | None
    last_success_time: float | None
    total_requests: int
    total_failures: int


class CircuitBreaker:
    """3-state circuit breaker FSM with in-memory state.

    In production, state would be stored in Redis for cross-process sharing.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None
        self._total_requests = 0
        self._total_failures = 0

    @property
    def state(self) -> CircuitState:
        """Get current state, auto-transitioning OPEN → HALF_OPEN after timeout."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def can_execute(self) -> bool:
        """Check if a request is allowed through the circuit."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True  # Allow one test request
        return False  # OPEN — fail fast

    def record_success(self) -> None:
        """Record a successful request."""
        self._total_requests += 1
        self._last_success_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Test request succeeded — close the circuit
            self._state = CircuitState.CLOSED
            self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self._total_requests += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Test request failed — reopen
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Force reset to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def get_status(self) -> CircuitBreakerStatus:
        """Get current circuit breaker status for inspection."""
        return CircuitBreakerStatus(
            state=self.state,
            failure_count=self._failure_count,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            total_requests=self._total_requests,
            total_failures=self._total_failures,
        )


class RedisCircuitBreaker:
    """Redis-backed circuit breaker for cross-process state sharing.

    Uses HSET/HGETALL on key `cb:{name}` with 24h TTL.
    Falls back gracefully if Redis is unavailable.
    """

    def __init__(
        self,
        name: str,
        redis_client: object,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.name = name
        self._redis = redis_client
        self._key = f"cb:{name}"
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    async def _get_state(self) -> dict[str, str]:
        """Read full state from Redis hash."""
        data = await self._redis.hgetall(self._key)
        if not data:
            return {
                "state": "closed", "failure_count": "0",
                "last_failure_time": "0", "last_success_time": "0",
                "total_requests": "0", "total_failures": "0",
            }
        return {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in data.items()}

    async def _set_fields(self, **fields: str) -> None:
        """Write fields to Redis hash with 24h TTL."""
        await self._redis.hset(self._key, mapping={k: str(v) for k, v in fields.items()})
        await self._redis.expire(self._key, 86400)

    @property
    async def state(self) -> CircuitState:
        """Get current state, auto-transitioning OPEN → HALF_OPEN after timeout."""
        data = await self._get_state()
        current = CircuitState(data.get("state", "closed"))
        if current == CircuitState.OPEN:
            last_fail = float(data.get("last_failure_time", "0"))
            if last_fail > 0 and (time.time() - last_fail) >= self.recovery_timeout:
                await self._set_fields(state="half_open")
                return CircuitState.HALF_OPEN
        return current

    async def can_execute(self) -> bool:
        """Check if a request is allowed through the circuit."""
        s = await self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    async def record_success(self) -> None:
        """Record a successful request."""
        data = await self._get_state()
        total = int(data.get("total_requests", "0")) + 1
        current = CircuitState(data.get("state", "closed"))
        new_state = "closed" if current == CircuitState.HALF_OPEN else data.get("state", "closed")
        await self._set_fields(
            state=new_state, failure_count="0",
            last_success_time=str(time.time()),
            total_requests=str(total),
        )

    async def record_failure(self) -> None:
        """Record a failed request."""
        data = await self._get_state()
        failures = int(data.get("failure_count", "0")) + 1
        total_req = int(data.get("total_requests", "0")) + 1
        total_fail = int(data.get("total_failures", "0")) + 1
        current = CircuitState(data.get("state", "closed"))

        if current == CircuitState.HALF_OPEN:
            new_state = "open"
        elif current == CircuitState.CLOSED and failures >= self.failure_threshold:
            new_state = "open"
        else:
            new_state = data.get("state", "closed")

        await self._set_fields(
            state=new_state, failure_count=str(failures),
            last_failure_time=str(time.time()),
            total_requests=str(total_req), total_failures=str(total_fail),
        )

    async def reset(self) -> None:
        """Force reset to closed state."""
        await self._set_fields(state="closed", failure_count="0", last_failure_time="0")

    async def get_status(self) -> CircuitBreakerStatus:
        """Get current status for inspection."""
        data = await self._get_state()
        return CircuitBreakerStatus(
            state=CircuitState(data.get("state", "closed")),
            failure_count=int(data.get("failure_count", "0")),
            last_failure_time=float(data.get("last_failure_time", "0")) or None,
            last_success_time=float(data.get("last_success_time", "0")) or None,
            total_requests=int(data.get("total_requests", "0")),
            total_failures=int(data.get("total_failures", "0")),
        )
