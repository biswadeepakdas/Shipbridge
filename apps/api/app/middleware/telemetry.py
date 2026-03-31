"""OpenTelemetry instrumentation for traces and metrics."""

import structlog
from fastapi import FastAPI

from app.config import get_settings

logger = structlog.get_logger()


def setup_telemetry(app: FastAPI) -> None:
    """Initialize OpenTelemetry tracing and FastAPI auto-instrumentation.

    Only activates when OTEL_EXPORTER_OTLP_ENDPOINT is configured.
    Falls back gracefully in development / test environments.
    """
    settings = get_settings()
    if not settings.otel_exporter_otlp_endpoint:
        logger.info("otel_skipped", reason="OTEL_EXPORTER_OTLP_ENDPOINT not set")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": "shipbridge-api",
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_initialized", endpoint=settings.otel_exporter_otlp_endpoint)

    except ImportError:
        logger.warning("otel_import_failed", reason="opentelemetry packages not installed")
    except Exception as e:
        logger.warning("otel_setup_failed", error=str(e))
