import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class LinearAdapter(ConnectorAdapter):
    """Connector for Linear — issues and projects."""

    adapter_type = "linear"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {"Authorization": self.api_key, "Content-Type": "application/json"}

    async def fetch(self, query: dict) -> dict[str, Any]:
        gql = query.get("query", "{ issues { nodes { id title state { name } } } }")
        async with httpx.AsyncClient() as client:
            response = await client.post(self.base_url, headers=self.headers, json={"query": gql})
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    headers=self.headers,
                    json={"query": "{ viewer { id } }"},
                    timeout=5,
                )
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
        issues = raw_data.get("data", {}).get("issues", {}).get("nodes", [])
        lines = [f"# Linear Issues ({len(issues)} items)\n"]
        for issue in issues:
            state = issue.get("state", {}).get("name", "Unknown")
            lines.append(f"- **[{state}]** {issue.get('title', 'Untitled')} (id: {issue.get('id', '')})")
        return NormalizedData(
            source="linear",
            data_type="issues",
            content="\n".join(lines),
            metadata={"issue_count": len(issues)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
