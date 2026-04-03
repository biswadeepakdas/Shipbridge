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
from app.routers.billing import router as billing_router
from app.routers.connectors import router as connectors_router
from app.routers.context import router as context_router
from app.routers.costs import router as costs_router
from app.routers.deployments import router as deployments_router
from app.routers.evals import router as evals_router
from app.routers.github import router as github_router
from app.routers.governance import router as governance_router
from app.routers.health import router as health_router
from app.routers.onboarding import router as onboarding_router
from app.routers.projects import router as projects_router
from app.routers.rules import router as rules_router
from app.routers.subscriptions import router as subscriptions_router
from app.routers.webhooks import router as webhooks_router
from app.routers.websocket import router as websocket_router # Import the new websocket router
from app.routers.audit import router as audit_router  # Chain-of-thought audit trail
from app.routers.events import router as events_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("shipbridge_api_starting", environment=settings.environment)

    # Validate JWT secret in production
    if settings.environment != "development" and settings.jwt_secret == "change-me-in-production":
        logger.critical("jwt_secret_insecure", message="JWT_SECRET must be changed in non-development environments!")
        raise RuntimeError("Insecure JWT_SECRET detected. Set JWT_SECRET environment variable.")

    # Initialize Sentry
    setup_sentry()

    # Initialize Redis connection pool (non-fatal)
    try:
        import redis.asyncio as aioredis

        _app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _app.state.redis.ping()
        logger.info("redis_connected")
    except Exception:
        _app.state.redis = None
        logger.warning("redis_unavailable", url=settings.redis_url)

    yield

    # Cleanup Redis
    if hasattr(_app.state, "redis") and _app.state.redis:
        await _app.state.redis.aclose()

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
from app.middleware.guardrails import GuardrailsMiddleware
app.add_middleware(GuardrailsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().web_base_url.split(",")],
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
app.include_router(billing_router)
app.include_router(onboarding_router)
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
app.include_router(websocket_router) # Include the new websocket router
app.include_router(audit_router)  # Chain-of-thought audit trail
app.include_router(events_router)
