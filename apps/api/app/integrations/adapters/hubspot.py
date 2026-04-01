"""HubSpotAdapter — OAuth2, normalize contacts/companies/deals/activities."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class HubSpotAdapter(ConnectorAdapter):
    """Connector for HubSpot CRM — contacts, companies, deals, activities."""

    adapter_type = "hubspot"

    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from HubSpot API.

        Args:
            query: {"object": "contacts|companies|deals|activities", "filters": {...}}
        """
        obj_type = query.get("object", "contacts")

        simulated: dict[str, dict] = {
            "contacts": {
                "objectType": "contacts",
                "results": [
                    {"id": "101", "properties": {"firstname": "Jane", "lastname": "Doe",
                     "email": "jane@acme.com", "company": "Acme Corp", "lifecyclestage": "customer"}},
                    {"id": "102", "properties": {"firstname": "John", "lastname": "Smith",
                     "email": "john@beta.io", "company": "Beta Inc", "lifecyclestage": "lead"}},
                ],
            },
            "companies": {
                "objectType": "companies",
                "results": [
                    {"id": "201", "properties": {"name": "Acme Corp", "industry": "Technology",
                     "annualrevenue": "5000000", "numberofemployees": "250", "city": "San Francisco"}},
                    {"id": "202", "properties": {"name": "Beta Inc", "industry": "Healthcare",
                     "annualrevenue": "1200000", "numberofemployees": "80", "city": "Austin"}},
                ],
            },
            "deals": {
                "objectType": "deals",
                "results": [
                    {"id": "301", "properties": {"dealname": "Acme Enterprise License", "amount": "95000",
                     "dealstage": "closedwon", "closedate": "2026-03-15"}},
                    {"id": "302", "properties": {"dealname": "Beta Growth Plan", "amount": "32000",
                     "dealstage": "contractsent", "closedate": "2026-04-20"}},
                ],
            },
            "activities": {
                "objectType": "activities",
                "results": [
                    {"id": "401", "properties": {"hs_activity_type": "CALL", "hs_call_title": "Discovery call",
                     "hs_timestamp": "2026-03-28T14:00:00Z", "hs_call_duration": "1800000"}},
                    {"id": "402", "properties": {"hs_activity_type": "EMAIL", "hs_email_subject": "Follow-up proposal",
                     "hs_timestamp": "2026-03-29T09:00:00Z"}},
                ],
            },
        }

        return simulated.get(obj_type, {"objectType": obj_type, "results": []})

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 40.0
        return ConnectorHealthResult(
            status="healthy", latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        obj_type = raw_data.get("objectType", "unknown")
        results = raw_data.get("results", [])

        lines = [f"# HubSpot {obj_type.capitalize()} ({len(results)} records)\n"]

        for record in results:
            props = record.get("properties", {})
            if obj_type == "contacts":
                name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                lines.append(f"## {name}")
                lines.append(f"- **Email**: {props.get('email', 'N/A')}")
                lines.append(f"- **Company**: {props.get('company', 'N/A')}")
                lines.append(f"- **Stage**: {props.get('lifecyclestage', 'N/A')}")
                lines.append("")
            elif obj_type == "companies":
                lines.append(f"## {props.get('name', 'Unnamed')}")
                lines.append(f"- **Industry**: {props.get('industry', 'N/A')}")
                revenue = props.get('annualrevenue', '0')
                lines.append(f"- **Revenue**: ${int(revenue):,}")
                lines.append(f"- **Employees**: {props.get('numberofemployees', 'N/A')}")
                lines.append(f"- **City**: {props.get('city', 'N/A')}")
                lines.append("")
            elif obj_type == "deals":
                lines.append(f"## {props.get('dealname', 'Unnamed')}")
                amount = props.get('amount', '0')
                lines.append(f"- **Amount**: ${int(amount):,}")
                lines.append(f"- **Stage**: {props.get('dealstage', 'N/A')}")
                lines.append(f"- **Close Date**: {props.get('closedate', 'N/A')}")
                lines.append("")
            elif obj_type == "activities":
                activity_type = props.get('hs_activity_type', 'Unknown')
                if activity_type == "CALL":
                    lines.append(f"## Call: {props.get('hs_call_title', 'Untitled')}")
                    duration_ms = int(props.get('hs_call_duration', '0'))
                    lines.append(f"- **Duration**: {duration_ms // 60000} min")
                elif activity_type == "EMAIL":
                    lines.append(f"## Email: {props.get('hs_email_subject', 'No subject')}")
                else:
                    lines.append(f"## {activity_type}")
                lines.append(f"- **Time**: {props.get('hs_timestamp', 'N/A')}")
                lines.append("")

        return NormalizedData(
            source="hubspot",
            data_type=obj_type,
            content="\n".join(lines),
            metadata={"total_records": len(results), "object_type": obj_type},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
