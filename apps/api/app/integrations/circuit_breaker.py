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
