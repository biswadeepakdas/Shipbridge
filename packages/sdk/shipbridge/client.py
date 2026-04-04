"""ShipBridge SDK client — lightweight instrumentation for custom Python agents.

Usage:
    from shipbridge import ShipBridgeClient

    client = ShipBridgeClient(
        api_url="https://api.shipbridge.dev",
        api_key="sb_key_...",
        project_id="your-project-id",
    )

    # Trace an LLM call
    with client.trace("llm_call", model="claude-3-5-sonnet") as span:
        result = your_llm.invoke(prompt)
        span.set_tokens(input_tokens=100, output_tokens=50)

    # Trace a tool call
    with client.trace("tool_call", tool_name="search_api") as span:
        data = search_api.query("user question")

    # Flush any buffered traces before shutdown
    client.flush()
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

import httpx


@dataclass
class SpanContext:
    """Mutable context for an in-progress trace span."""

    trace_id: str
    span_id: str
    operation: str
    model: str | None = None
    tool_name: str | None = None
    parent_span_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _start_time: float = 0.0
    _status: str = "ok"

    def set_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Record token usage for this span."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def set_error(self, error: str) -> None:
        """Mark this span as errored."""
        self._status = "error"
        self.error_message = error

    def set_metadata(self, key: str, value: Any) -> None:
        """Attach metadata to this span."""
        self.metadata[key] = value


class ShipBridgeClient:
    """Client for sending traces and events to ShipBridge.

    Traces are buffered in memory and flushed in batches for efficiency.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        project_id: str,
        *,
        batch_size: int = 20,
        auto_flush: bool = True,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.project_id = project_id
        self.batch_size = batch_size
        self.auto_flush = auto_flush
        self._buffer: list[dict[str, Any]] = []
        self._current_trace_id: str | None = None

    @contextmanager
    def trace(
        self,
        operation: str,
        *,
        model: str | None = None,
        tool_name: str | None = None,
        parent_span_id: str | None = None,
    ) -> Generator[SpanContext, None, None]:
        """Context manager that records a trace span and buffers it for sending.

        Example::

            with client.trace("llm_call", model="claude-3-5-sonnet") as span:
                result = llm.invoke(prompt)
                span.set_tokens(input_tokens=100, output_tokens=50)
        """
        trace_id = self._current_trace_id or uuid.uuid4().hex
        span = SpanContext(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex,
            operation=operation,
            model=model,
            tool_name=tool_name,
            parent_span_id=parent_span_id,
            _start_time=time.monotonic(),
        )

        prev_trace_id = self._current_trace_id
        self._current_trace_id = trace_id

        try:
            yield span
        except Exception as exc:
            span.set_error(str(exc))
            raise
        finally:
            duration_ms = (time.monotonic() - span._start_time) * 1000
            self._current_trace_id = prev_trace_id

            trace_data = {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "operation": span.operation,
                "status": span._status,
                "duration_ms": round(duration_ms, 2),
                "input_tokens": span.input_tokens,
                "output_tokens": span.output_tokens,
                "model": span.model,
                "tool_name": span.tool_name,
                "error_message": span.error_message,
                "metadata": span.metadata,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self._buffer.append(trace_data)

            if self.auto_flush and len(self._buffer) >= self.batch_size:
                self.flush()

    def record_trace(self, trace_data: dict[str, Any]) -> None:
        """Manually record a single trace. Use `trace()` context manager instead when possible."""
        self._buffer.append(trace_data)
        if self.auto_flush and len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        """Send all buffered traces to ShipBridge."""
        if not self._buffer:
            return

        batch = self._buffer[:]
        self._buffer.clear()

        try:
            with httpx.Client(timeout=10.0) as http:
                resp = http.post(
                    f"{self.api_url}/api/v1/projects/{self.project_id}/traces",
                    json={"traces": batch},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
        except Exception:
            # Re-buffer on failure so traces aren't lost
            self._buffer = batch + self._buffer

    @property
    def pending_count(self) -> int:
        """Number of traces waiting to be flushed."""
        return len(self._buffer)
