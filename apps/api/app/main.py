"""ShipBridge API — FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import AppError, app_error_handler
from app.middleware.logging import setup_logging
from app.routers.health import router as health_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("shipbridge_api_starting", environment=settings.environment)

    # Test Redis connectivity (non-fatal)
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        logger.info("redis_connected")
    except Exception:
        logger.warning("redis_unavailable", url=settings.redis_url)

    yield

    logger.info("shipbridge_api_shutting_down")


app = FastAPI(
    title="ShipBridge API",
    description="Pilot-to-Production Platform for AI Agent Teams",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)

# Routers
app.include_router(health_router)
