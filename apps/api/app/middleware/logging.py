"""Structured JSON logging with tenant_id and trace_id on every log line."""

import logging
import uuid

import structlog


def setup_logging(log_level: str = "DEBUG") -> None:
    """Configure structlog for JSON output with request context."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set root logger level
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.DEBUG))


def generate_trace_id() -> str:
    """Generate a unique trace ID for request correlation."""
    return uuid.uuid4().hex[:16]


def bind_request_context(tenant_id: str | None = None, trace_id: str | None = None) -> None:
    """Bind tenant_id and trace_id to structlog context for the current request."""
    ctx: dict[str, str] = {}
    if tenant_id:
        ctx["tenant_id"] = tenant_id
    if trace_id:
        ctx["trace_id"] = trace_id
    if ctx:
        structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    """Clear structlog context vars at end of request."""
    structlog.contextvars.clear_contextvars()
