import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class AirtableAdapter(ConnectorAdapter):
    """Connector for Airtable — bases and tables."""

    adapter_type = "airtable"

    def __init__(self, api_key: str, base_id: str = "") -> None:
        self.api_key = api_key
        self.base_id = base_id
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def fetch(self, query: dict) -> dict[str, Any]:
        table_name = query.get("table", "")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{table_name}", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("https://api.airtable.com/v0/meta/bases", headers=self.headers, timeout=5)
                status = "healthy" if response.status_code < 400 else "degraded"
        except Exception:
            status = "unhealthy"
        latency = (time.monotonic() - start) * 1000
        return ConnectorHealthResult(
            status=status,
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        records = raw_data.get("records", [])
        lines = [f"# Airtable Records ({len(records)} rows)\n"]
        for r in records:
            fields = r.get("fields", {})
            for k, v in fields.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        return NormalizedData(
            source="airtable",
            data_type="table",
            content="\n".join(lines),
            metadata={"record_count": len(records)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
