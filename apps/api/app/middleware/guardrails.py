import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    _presidio_available = True
except ImportError:
    _presidio_available = False
    logger.warning("presidio-analyzer/anonymizer not installed. GuardrailsMiddleware will pass through without PII scanning.")


class GuardrailsMiddleware(BaseHTTPMiddleware):
    """Intercepts API responses and redacts PII from JSON bodies."""

    def __init__(self, app):
        super().__init__(app)
        if _presidio_available:
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
        else:
            self.analyzer = None
            self.anonymizer = None

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not _presidio_available:
            return response

        monitored_paths = ("/api/v1/projects", "/api/v1/rules")
        content_type = response.headers.get("content-type", "")

        if not any(request.url.path.startswith(p) for p in monitored_paths):
            return response
        if "application/json" not in content_type:
            return response

        body_bytes = b""
        async for chunk in response.body_iterator:
            body_bytes += chunk

        try:
            body_text = body_bytes.decode("utf-8")
            results = self.analyzer.analyze(text=body_text, language="en",
                                            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])
            if results:
                logger.warning(
                    "PII detected in response for path %s — redacting %d entities.",
                    request.url.path, len(results)
                )
                from presidio_anonymizer.entities import OperatorConfig
                anonymized = self.anonymizer.anonymize(
                    text=body_text,
                    analyzer_results=results,
                    operators={"DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED>"})}
                )
                body_bytes = anonymized.text.encode("utf-8")
        except Exception as exc:
            logger.error("GuardrailsMiddleware error: %s", exc)

        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
