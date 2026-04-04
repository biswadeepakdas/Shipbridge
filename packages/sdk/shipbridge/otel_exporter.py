"""OpenTelemetry SpanExporter that sends spans to ShipBridge trace ingestion.

Usage:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from shipbridge.otel_exporter import ShipBridgeSpanExporter

    exporter = ShipBridgeSpanExporter(
        api_url="https://api.shipbridge.dev",
        api_key="sb_key_...",
        project_id="your-project-id",
    )
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))
"""

from __future__ import annotations

from typing import Sequence

import httpx


class ShipBridgeSpanExporter:
    """Export OpenTelemetry spans to ShipBridge for production readiness scoring.

    Implements the SpanExporter interface so it can be used with
    ``BatchSpanProcessor`` or ``SimpleSpanProcessor``.
    """

    def __init__(self, api_url: str, api_key: str, project_id: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.project_id = project_id

    def export(self, spans: Sequence) -> int:
        """Convert OTel spans to ShipBridge trace format and POST batch.

        Returns 0 (SUCCESS) or 1 (FAILURE) per the SpanExportResult convention.
        """
        traces = []
        for span in spans:
            ctx = span.get_span_context()
            duration_ns = (span.end_time or 0) - (span.start_time or 0)
            duration_ms = duration_ns / 1_000_000

            attrs = dict(span.attributes) if span.attributes else {}
            trace_data = {
                "trace_id": format(ctx.trace_id, "032x") if ctx else "",
                "span_id": format(ctx.span_id, "016x") if ctx else "",
                "parent_span_id": (
                    format(span.parent.span_id, "016x")
                    if span.parent and span.parent.span_id
                    else None
                ),
                "operation": span.name,
                "status": "error" if span.status and span.status.is_ok is False else "ok",
                "duration_ms": round(duration_ms, 2),
                "input_tokens": int(attrs.get("llm.input_tokens", 0)),
                "output_tokens": int(attrs.get("llm.output_tokens", 0)),
                "model": attrs.get("llm.model", attrs.get("gen_ai.request.model")),
                "tool_name": attrs.get("tool.name"),
                "error_message": (
                    span.status.description
                    if span.status and span.status.description
                    else None
                ),
                "metadata": {k: str(v) for k, v in attrs.items()},
            }
            traces.append(trace_data)

        if not traces:
            return 0  # SUCCESS

        try:
            with httpx.Client(timeout=10.0) as http:
                resp = http.post(
                    f"{self.api_url}/api/v1/projects/{self.project_id}/traces",
                    json={"traces": traces},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
            return 0  # SUCCESS
        except Exception:
            return 1  # FAILURE

    def shutdown(self) -> None:
        """No-op shutdown — HTTP client is created per-flush."""

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """No-op — spans are sent synchronously in export()."""
        return True
