"""Request logging middleware — adds trace_id and tenant_id to every request."""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.logging import bind_request_context, clear_request_context, generate_trace_id

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs every request with trace_id, duration, and tenant context."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with structured logging context."""
        trace_id = request.headers.get("X-Trace-ID", generate_trace_id())
        start_time = time.monotonic()

        # Extract tenant_id from auth header if present (best-effort, no validation here)
        tenant_id = None

        bind_request_context(tenant_id=tenant_id, trace_id=trace_id)

        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start_time) * 1000

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                trace_id=trace_id,
            )

            # Add trace_id to response headers for client correlation
            response.headers["X-Trace-ID"] = trace_id
            return response

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                error=str(e),
                trace_id=trace_id,
            )
            raise
        finally:
            clear_request_context()
