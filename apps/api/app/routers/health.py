"""Health check endpoint — primary Day 1 deliverable."""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.response import APIResponse

router = APIRouter(tags=["health"])


class HealthCheck(BaseModel):
    """Health check response payload."""

    status: str
    service: str
    version: str
    timestamp: str
    checks: dict = {}


@router.get("/health", response_model=APIResponse[HealthCheck])
async def health() -> APIResponse[HealthCheck]:
    """Return service health with dependency checks."""
    checks: dict = {}

    # Postgres check
    try:
        from sqlalchemy import text

        from app.db import async_session

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"

    # Redis check
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        r = aioredis.from_url(get_settings().redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    status = "ok" if all_ok else "degraded"

    return APIResponse(
        data=HealthCheck(
            status=status,
            service="api",
            version="0.1.0",
            timestamp=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )
    )
