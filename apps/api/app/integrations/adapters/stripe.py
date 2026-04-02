import time
from datetime import datetime, timezone
from typing import Any

import stripe

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class StripeAdapter(ConnectorAdapter):
    """Connector for Stripe — customers, payments, subscriptions."""

    adapter_type = "stripe"

    def __init__(self, api_key: str) -> None:
        stripe.api_key = api_key

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch Stripe data. Query: {\"type\": \"customer|payment|subscription\", \"id\": \"...\"}"""
        obj_type = query.get("type", "customer")
        obj_id = query.get("id")
        if obj_type == "customer" and obj_id:
            return stripe.Customer.retrieve(obj_id)
        elif obj_type == "payment" and obj_id:
            return stripe.PaymentIntent.retrieve(obj_id)
        elif obj_type == "subscription" and obj_id:
            return stripe.Subscription.retrieve(obj_id)
        else:
            raise ValueError(f"Unsupported Stripe object type or missing ID: {obj_type}")

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        try:
            stripe.Customer.list(limit=1)
            status = "healthy"
        except Exception:
            status = "unhealthy"
        latency = (time.monotonic() - start) * 1000
        return ConnectorHealthResult(
            status=status,
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        obj_type = raw_data.get("object", "unknown")
        lines = [f"# Stripe {obj_type.capitalize()}\n"]
        for k, v in raw_data.items():
            if k not in ("object", "id") and not k.startswith("_"):
                lines.append(f"- **{k}**: {v}")
        return NormalizedData(
            source="stripe",
            data_type=obj_type,
            content="\n".join(lines),
            metadata={"object_id": raw_data.get("id", "")},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
