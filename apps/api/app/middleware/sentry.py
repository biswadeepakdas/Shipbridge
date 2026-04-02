"""Sentry error tracking integration."""

import structlog

from app.config import get_settings

logger = structlog.get_logger()


def setup_sentry() -> None:
    """Initialize Sentry SDK for error tracking.

    Only activates when SENTRY_DSN is configured.
    Falls back gracefully in development / test environments.
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        logger.info("sentry_skipped", reason="SENTRY_DSN not set")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"shipbridge-api@0.1.0",
            traces_sample_rate=0.1 if settings.environment == "production" else 1.0,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            send_default_pii=False,
        )
        logger.info("sentry_initialized", environment=settings.environment)

    except ImportError:
        logger.warning("sentry_import_failed", reason="sentry-sdk not installed")
    except Exception as e:
        logger.warning("sentry_setup_failed", error=str(e))
