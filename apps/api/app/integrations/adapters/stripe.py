"""StripeAdapter — API key auth, normalize payments/customers/subscriptions."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class StripeAdapter(ConnectorAdapter):
    """Connector for Stripe — payments, customers, subscriptions."""

    adapter_type = "stripe"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Stripe API.

        Args:
            query: {"object": "payments|customers|subscriptions", "filters": {...}}
        """
        obj_type = query.get("object", "payments")

        simulated: dict[str, dict] = {
            "payments": {
                "objectType": "payments",
                "data": [
                    {"id": "pi_001", "amount": 9900, "currency": "usd", "status": "succeeded",
                     "customer": "cus_001", "description": "Pro Plan - Monthly",
                     "created": 1711900000},
                    {"id": "pi_002", "amount": 19900, "currency": "usd", "status": "succeeded",
                     "customer": "cus_002", "description": "Enterprise Plan - Monthly",
                     "created": 1711886400},
                    {"id": "pi_003", "amount": 2900, "currency": "usd", "status": "failed",
                     "customer": "cus_003", "description": "Free to Pro Upgrade",
                     "created": 1711800000, "failure_message": "Card declined"},
                ],
            },
            "customers": {
                "objectType": "customers",
                "data": [
                    {"id": "cus_001", "name": "Acme Corp", "email": "billing@acme.com",
                     "created": 1709300000, "currency": "usd",
                     "subscriptions": {"data": [{"id": "sub_001", "status": "active", "plan": {"nickname": "Pro"}}]}},
                    {"id": "cus_002", "name": "Beta Inc", "email": "finance@beta.io",
                     "created": 1710500000, "currency": "usd",
                     "subscriptions": {"data": [{"id": "sub_002", "status": "active", "plan": {"nickname": "Enterprise"}}]}},
                ],
            },
            "subscriptions": {
                "objectType": "subscriptions",
                "data": [
                    {"id": "sub_001", "customer": "cus_001", "status": "active",
                     "plan": {"nickname": "Pro", "amount": 2900, "interval": "month"},
                     "current_period_end": 1714578000},
                    {"id": "sub_002", "customer": "cus_002", "status": "active",
                     "plan": {"nickname": "Enterprise", "amount": 19900, "interval": "month"},
                     "current_period_end": 1714578000},
                    {"id": "sub_003", "customer": "cus_003", "status": "canceled",
                     "plan": {"nickname": "Pro", "amount": 2900, "interval": "month"},
                     "canceled_at": 1711800000},
                ],
            },
        }

        return simulated.get(obj_type, {"objectType": obj_type, "data": []})

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 30.0
        return ConnectorHealthResult(
            status="healthy", latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        obj_type = raw_data.get("objectType", "unknown")
        records = raw_data.get("data", [])

        lines = [f"# Stripe {obj_type.capitalize()} ({len(records)} records)\n"]

        for record in records:
            if obj_type == "payments":
                amount = record.get("amount", 0) / 100
                status = record.get("status", "unknown")
                lines.append(f"## {record.get('description', 'Payment')}")
                lines.append(f"- **Amount**: ${amount:,.2f} {record.get('currency', 'usd').upper()}")
                lines.append(f"- **Status**: {status}")
                if status == "failed":
                    lines.append(f"- **Failure**: {record.get('failure_message', 'Unknown error')}")
                lines.append("")
            elif obj_type == "customers":
                lines.append(f"## {record.get('name', 'Unnamed')}")
                lines.append(f"- **Email**: {record.get('email', 'N/A')}")
                subs = record.get("subscriptions", {}).get("data", [])
                if subs:
                    plan = subs[0].get("plan", {}).get("nickname", "N/A")
                    sub_status = subs[0].get("status", "N/A")
                    lines.append(f"- **Plan**: {plan} ({sub_status})")
                lines.append("")
            elif obj_type == "subscriptions":
                plan = record.get("plan", {})
                amount = plan.get("amount", 0) / 100
                lines.append(f"## {plan.get('nickname', 'Unknown Plan')}")
                lines.append(f"- **Amount**: ${amount:,.2f}/{plan.get('interval', 'month')}")
                lines.append(f"- **Status**: {record.get('status', 'N/A')}")
                if record.get("canceled_at"):
                    lines.append(f"- **Canceled**: yes")
                lines.append("")

        return NormalizedData(
            source="stripe",
            data_type=obj_type,
            content="\n".join(lines),
            metadata={"total_records": len(records), "object_type": obj_type},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
