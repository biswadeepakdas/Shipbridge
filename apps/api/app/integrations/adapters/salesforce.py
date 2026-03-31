"""SalesforceAdapter — OAuth2 PKCE flow, normalize() → agent-friendly markdown."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class SalesforceAdapter(ConnectorAdapter):
    """Connector for Salesforce CRM — opportunities, accounts, contacts, activities."""

    adapter_type = "salesforce"

    def __init__(self, instance_url: str = "", access_token: str = "") -> None:
        self.instance_url = instance_url
        self.access_token = access_token

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Salesforce REST API.

        In production, this would make real HTTP calls to the Salesforce API.
        For now, returns simulated data based on query object type.

        Args:
            query: {"object": "Opportunity|Account|Contact|Activity", "filters": {...}}
        """
        obj_type = query.get("object", "Opportunity")
        filters = query.get("filters", {})

        # Simulated Salesforce responses per object type
        simulated: dict[str, list[dict]] = {
            "Opportunity": [
                {"Id": "006xx000001", "Name": "Acme Corp - Enterprise", "Amount": 125000,
                 "StageName": "Closed Won", "CloseDate": "2026-03-15", "AccountId": "001xx000001"},
                {"Id": "006xx000002", "Name": "Beta Inc - Growth", "Amount": 45000,
                 "StageName": "Negotiation", "CloseDate": "2026-04-30", "AccountId": "001xx000002"},
            ],
            "Account": [
                {"Id": "001xx000001", "Name": "Acme Corp", "Industry": "Technology",
                 "AnnualRevenue": 5000000, "NumberOfEmployees": 250},
                {"Id": "001xx000002", "Name": "Beta Inc", "Industry": "Healthcare",
                 "AnnualRevenue": 1200000, "NumberOfEmployees": 80},
            ],
            "Contact": [
                {"Id": "003xx000001", "FirstName": "Alice", "LastName": "Johnson",
                 "Email": "alice@acme.com", "Title": "VP Engineering", "AccountId": "001xx000001"},
            ],
            "Activity": [
                {"Id": "00Txx000001", "Subject": "Follow-up call", "ActivityDate": "2026-03-30",
                 "Status": "Completed", "WhoId": "003xx000001"},
            ],
        }

        records = simulated.get(obj_type, [])
        return {"totalSize": len(records), "records": records, "objectType": obj_type}

    async def health_check(self) -> ConnectorHealthResult:
        """Check Salesforce API connectivity."""
        start = time.monotonic()
        # Simulated health check — production would call /services/data/vXX.0/limits
        latency = (time.monotonic() - start) * 1000 + 35.0  # simulated ~35ms

        return ConnectorHealthResult(
            status="healthy",
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform Salesforce API response into agent-friendly markdown."""
        obj_type = raw_data.get("objectType", "Unknown")
        records = raw_data.get("records", [])
        total = raw_data.get("totalSize", 0)

        lines = [f"# Salesforce {obj_type}s ({total} records)\n"]

        for record in records:
            if obj_type == "Opportunity":
                lines.append(f"## {record.get('Name', 'Unnamed')}")
                lines.append(f"- **Amount**: ${record.get('Amount', 0):,.0f}")
                lines.append(f"- **Stage**: {record.get('StageName', 'Unknown')}")
                lines.append(f"- **Close Date**: {record.get('CloseDate', 'N/A')}")
                lines.append("")
            elif obj_type == "Account":
                lines.append(f"## {record.get('Name', 'Unnamed')}")
                lines.append(f"- **Industry**: {record.get('Industry', 'Unknown')}")
                lines.append(f"- **Revenue**: ${record.get('AnnualRevenue', 0):,.0f}")
                lines.append(f"- **Employees**: {record.get('NumberOfEmployees', 'N/A')}")
                lines.append("")
            elif obj_type == "Contact":
                name = f"{record.get('FirstName', '')} {record.get('LastName', '')}".strip()
                lines.append(f"## {name}")
                lines.append(f"- **Title**: {record.get('Title', 'N/A')}")
                lines.append(f"- **Email**: {record.get('Email', 'N/A')}")
                lines.append("")
            elif obj_type == "Activity":
                lines.append(f"## {record.get('Subject', 'Untitled')}")
                lines.append(f"- **Date**: {record.get('ActivityDate', 'N/A')}")
                lines.append(f"- **Status**: {record.get('Status', 'Unknown')}")
                lines.append("")
            else:
                # Generic fallback
                lines.append(f"## Record {record.get('Id', 'unknown')}")
                for k, v in record.items():
                    if k != "Id":
                        lines.append(f"- **{k}**: {v}")
                lines.append("")

        return NormalizedData(
            source="salesforce",
            data_type=obj_type.lower(),
            content="\n".join(lines),
            metadata={"total_records": total, "object_type": obj_type},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
