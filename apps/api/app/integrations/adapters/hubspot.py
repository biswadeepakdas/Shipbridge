import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInput
import structlog

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData

logger = structlog.get_logger()


class HubSpotAdapter(ConnectorAdapter):
    """Connector for HubSpot CRM — contacts, companies, deals, activities."""

    adapter_type = "hubspot"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.client = HubSpot(api_key=api_key)

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from HubSpot API.

        Args:
            query: {"object": "contacts|companies|deals|activities", "filters": {...}}
        """
        obj_type = query.get("object", "contacts")

        try:
            if obj_type == "contacts":
                api_response = self.client.crm.contacts.basic_api.get_page(limit=query.get("limit", 10))
                return {"objectType": "contacts", "results": [contact.to_dict() for contact in api_response.results]}
            elif obj_type == "companies":
                api_response = self.client.crm.companies.basic_api.get_page(limit=query.get("limit", 10))
                return {"objectType": "companies", "results": [company.to_dict() for company in api_response.results]}
            elif obj_type == "deals":
                api_response = self.client.crm.deals.basic_api.get_page(limit=query.get("limit", 10))
                return {"objectType": "deals", "results": [deal.to_dict() for deal in api_response.results]}
            elif obj_type == "activities":
                # HubSpot activities API is more complex, this is a simplified example
                # You might need to use specific activity APIs like calls, emails, etc.
                logger.warning("hubspot_fetch_activities_unsupported", message="Fetching activities directly is not fully supported via basic API.")
                return {"objectType": "activities", "results": []}
            else:
                raise ValueError(f"Unsupported HubSpot object type: {obj_type}")
        except Exception as e:
            logger.error("hubspot_api_error", method="fetch", object_type=obj_type, error=str(e))
            raise

    async def health_check(self) -> ConnectorHealthResult:
        """Checks HubSpot API connectivity by attempting to fetch a small number of contacts."""
        start = time.monotonic()
        try:
            # Attempt to fetch a small number of contacts to verify connectivity
            self.client.crm.contacts.basic_api.get_page(limit=1)
            status = "healthy"
        except Exception as e:
            status = "unhealthy"
            logger.error("hubspot_health_check_error", error=str(e))
        latency = (time.monotonic() - start) * 1000

        return ConnectorHealthResult(
            status=status,
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transforms HubSpot API response into agent-friendly markdown."""
        obj_type = raw_data.get("objectType", "unknown")
        results = raw_data.get("results", [])

        lines = [f"# HubSpot {obj_type.capitalize()} ({len(results)} records)\n"]

        for record in results:
            props = record.get("properties", {})
            if obj_type == "contacts":
                name = f"{props.get("firstname", "")} {props.get("lastname", "")}".strip()
                lines.append(f"## {name}")
                lines.append(f"- **Email**: {props.get("email", "N/A")}")
                lines.append(f"- **Company**: {props.get("company", "N/A")}")
                lines.append(f"- **Stage**: {props.get("lifecyclestage", "N/A")}")
                lines.append("")
            elif obj_type == "companies":
                lines.append(f"## {props.get("name", "Unnamed")}")
                lines.append(f"- **Industry**: {props.get("industry", "N/A")}")
                revenue = props.get("annualrevenue", "0")
                lines.append(f"- **Revenue**: ${int(float(revenue)):,}")
                lines.append(f"- **Employees**: {props.get("numberofemployees", "N/A")}")
                lines.append(f"- **City**: {props.get("city", "N/A")}")
                lines.append("")
            elif obj_type == "deals":
                lines.append(f"## {props.get("dealname", "Unnamed")}")
                amount = props.get("amount", "0")
                lines.append(f"- **Amount**: ${int(float(amount)):,}")
                lines.append(f"- **Stage**: {props.get("dealstage", "N/A")}")
                lines.append(f"- **Close Date**: {props.get("closedate", "N/A")}")
                lines.append("")
            elif obj_type == "activities":
                # Simplified normalization for activities
                activity_type = props.get("hs_activity_type", "Unknown")
                lines.append(f"## {activity_type} Activity")
                lines.append(f"- **Subject**: {props.get("hs_email_subject", props.get("hs_call_title", "N/A"))}")
                lines.append(f"- **Time**: {props.get("hs_timestamp", "N/A")}")
                lines.append("")

        return NormalizedData(
            source="hubspot",
            data_type=obj_type,
            content="\n".join(lines),
            metadata={"total_records": len(results), "object_type": obj_type},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
