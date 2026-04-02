"""Rate limiting middleware — in-memory per-tenant rate limiter.

100 req/min per tenant. Production uses Redis sliding window.
"""

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

import structlog

logger = structlog.get_logger()

DEFAULT_RATE = 100  # requests
DEFAULT_WINDOW = 60  # seconds


class RateLimiter:
    """In-memory sliding window rate limiter. Production uses Redis."""

    def __init__(self, max_requests: int = DEFAULT_RATE, window_seconds: int = DEFAULT_WINDOW) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, remaining, reset_seconds)."""
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Clean old requests
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        count = len(self._requests[key])
        remaining = max(0, self.max_requests - count)

        if count >= self.max_requests:
            oldest = self._requests[key][0] if self._requests[key] else now
            reset_in = int(oldest + self.window_seconds - now) + 1
            return False, 0, reset_in

        self._requests[key].append(now)
        return True, remaining - 1, self.window_seconds

    def reset(self, key: str | None = None) -> None:
        if key:
            self._requests.pop(key, None)
        else:
            self._requests.clear()


# Singleton
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces rate limits per tenant/IP."""

    # Paths exempt from rate limiting
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip exempt paths
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Extract rate limit key: tenant from auth header or IP
        key = self._extract_key(request)

        allowed, remaining, reset_in = rate_limiter.is_allowed(key)

        if not allowed:
            logger.warning("rate_limited", key=key, path=path)
            return JSONResponse(
                status_code=429,
                content={
                    "data": None,
                    "error": {"code": "RATE_LIMITED", "message": f"Rate limit exceeded. Retry after {reset_in}s", "details": {}},
                    "meta": {},
                },
                headers={
                    "X-RateLimit-Limit": str(DEFAULT_RATE),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_in),
                    "Retry-After": str(reset_in),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(DEFAULT_RATE)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    @staticmethod
    def _extract_key(request: Request) -> str:
        """Extract rate limit key from request."""
        # Try to get tenant from auth header
        auth = request.headers.get("authorization", "")
        api_key = request.headers.get("x-api-key", "")
        if auth:
            return f"auth:{auth[:20]}"
        if api_key:
            return f"key:{api_key[:12]}"
        # Fallback to IP
        client = request.client
        ip = client.host if client else "unknown"
        return f"ip:{ip}"
