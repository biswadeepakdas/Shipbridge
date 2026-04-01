"""ShipBridge API — FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import AppError, app_error_handler
from app.middleware.logging import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.sentry import setup_sentry
from app.middleware.telemetry import setup_telemetry
from app.routers.auth import router as auth_router
from app.routers.connectors import router as connectors_router
from app.routers.context import router as context_router
from app.routers.costs import router as costs_router
from app.routers.deployments import router as deployments_router
from app.routers.evals import router as evals_router
from app.routers.github import router as github_router
from app.routers.governance import router as governance_router
from app.routers.health import router as health_router
from app.routers.projects import router as projects_router
from app.routers.rules import router as rules_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.webhooks import router as webhooks_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("shipbridge_api_starting", environment=settings.environment)

    # Initialize Sentry
    setup_sentry()

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

# Middleware (order matters — outermost first)
app.add_middleware(RequestLoggingMiddleware)
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry auto-instrumentation
setup_telemetry(app)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)

# Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(evals_router)
app.include_router(connectors_router)
app.include_router(context_router)
app.include_router(costs_router)
app.include_router(governance_router)
app.include_router(deployments_router)
app.include_router(rules_router)
app.include_router(subscriptions_router)
app.include_router(webhooks_router)
app.include_router(github_router)
