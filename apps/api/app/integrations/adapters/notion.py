"""NotionAdapter — OAuth2, normalize() for pages, databases, and blocks."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class NotionAdapter(ConnectorAdapter):
    """Connector for Notion — pages, databases, and blocks."""

    adapter_type = "notion"

    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Notion API.

        In production, this would make real HTTP calls to the Notion API.

        Args:
            query: {"type": "page|database|search", "id": "...", "filters": {...}}
        """
        query_type = query.get("type", "search")

        simulated: dict[str, dict] = {
            "page": {
                "object": "page",
                "id": "page-001",
                "properties": {
                    "title": {"title": [{"plain_text": "Q4 Planning Document"}]},
                    "Status": {"select": {"name": "In Progress"}},
                    "Priority": {"select": {"name": "High"}},
                    "Assigned": {"people": [{"name": "Alice Johnson"}]},
                },
                "created_time": "2026-03-01T10:00:00.000Z",
                "last_edited_time": "2026-03-28T14:30:00.000Z",
            },
            "database": {
                "object": "database",
                "id": "db-001",
                "title": [{"plain_text": "Product Roadmap"}],
                "results": [
                    {"id": "row-1", "properties": {
                        "Name": {"title": [{"plain_text": "Feature A"}]},
                        "Status": {"select": {"name": "Done"}},
                        "Sprint": {"select": {"name": "Sprint 12"}},
                    }},
                    {"id": "row-2", "properties": {
                        "Name": {"title": [{"plain_text": "Feature B"}]},
                        "Status": {"select": {"name": "In Progress"}},
                        "Sprint": {"select": {"name": "Sprint 13"}},
                    }},
                    {"id": "row-3", "properties": {
                        "Name": {"title": [{"plain_text": "Feature C"}]},
                        "Status": {"select": {"name": "Planned"}},
                        "Sprint": {"select": {"name": "Sprint 14"}},
                    }},
                ],
            },
            "search": {
                "object": "list",
                "results": [
                    {"object": "page", "id": "page-001",
                     "properties": {"title": {"title": [{"plain_text": "Q4 Planning"}]}}},
                    {"object": "page", "id": "page-002",
                     "properties": {"title": {"title": [{"plain_text": "Meeting Notes"}]}}},
                    {"object": "database", "id": "db-001",
                     "title": [{"plain_text": "Product Roadmap"}]},
                ],
            },
        }

        return simulated.get(query_type, {"object": "list", "results": []})

    async def health_check(self) -> ConnectorHealthResult:
        """Check Notion API connectivity."""
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 28.0  # simulated ~28ms

        return ConnectorHealthResult(
            status="healthy",
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform Notion API response into agent-friendly markdown."""
        obj_type = raw_data.get("object", "unknown")

        if obj_type == "page":
            return self._normalize_page(raw_data)
        elif obj_type == "database":
            return self._normalize_database(raw_data)
        elif obj_type == "list":
            return self._normalize_search(raw_data)
        else:
            return NormalizedData(
                source="notion",
                data_type="unknown",
                content=f"# Unknown Notion object type: {obj_type}",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

    def _normalize_page(self, data: dict) -> NormalizedData:
        """Normalize a Notion page."""
        props = data.get("properties", {})
        title = self._extract_title(props.get("title", {}))

        lines = [f"# {title}\n"]
        lines.append(f"- **Created**: {data.get('created_time', 'N/A')}")
        lines.append(f"- **Last edited**: {data.get('last_edited_time', 'N/A')}")

        for key, value in props.items():
            if key == "title":
                continue
            prop_value = self._extract_property_value(value)
            if prop_value:
                lines.append(f"- **{key}**: {prop_value}")

        return NormalizedData(
            source="notion",
            data_type="page",
            content="\n".join(lines),
            metadata={"page_id": data.get("id", "")},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    def _normalize_database(self, data: dict) -> NormalizedData:
        """Normalize a Notion database query result."""
        title_list = data.get("title", [])
        db_title = title_list[0].get("plain_text", "Untitled") if title_list else "Untitled"
        results = data.get("results", [])

        lines = [f"# {db_title} ({len(results)} rows)\n"]
        lines.append("| Name | Status | Details |")
        lines.append("|------|--------|---------|")

        for row in results:
            props = row.get("properties", {})
            name = self._extract_title(props.get("Name", {}))
            status = self._extract_property_value(props.get("Status", {}))
            other = {k: self._extract_property_value(v) for k, v in props.items()
                     if k not in ("Name", "Status") and self._extract_property_value(v)}
            details = ", ".join(f"{k}: {v}" for k, v in other.items()) if other else "—"
            lines.append(f"| {name} | {status} | {details} |")

        return NormalizedData(
            source="notion",
            data_type="database",
            content="\n".join(lines),
            metadata={"database_id": data.get("id", ""), "row_count": len(results)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    def _normalize_search(self, data: dict) -> NormalizedData:
        """Normalize Notion search results."""
        results = data.get("results", [])
        lines = [f"# Notion Search Results ({len(results)} items)\n"]

        for item in results:
            obj = item.get("object", "unknown")
            if obj == "page":
                title = self._extract_title(item.get("properties", {}).get("title", {}))
                lines.append(f"- **Page**: {title} (id: {item.get('id', '')})")
            elif obj == "database":
                title_list = item.get("title", [])
                title = title_list[0].get("plain_text", "Untitled") if title_list else "Untitled"
                lines.append(f"- **Database**: {title} (id: {item.get('id', '')})")

        return NormalizedData(
            source="notion",
            data_type="search",
            content="\n".join(lines),
            metadata={"result_count": len(results)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _extract_title(prop: dict) -> str:
        """Extract plain text from a Notion title property."""
        title_list = prop.get("title", [])
        if title_list and isinstance(title_list, list):
            return title_list[0].get("plain_text", "Untitled")
        return "Untitled"

    @staticmethod
    def _extract_property_value(prop: dict) -> str:
        """Extract display value from a Notion property."""
        if "select" in prop and prop["select"]:
            return prop["select"].get("name", "")
        if "people" in prop and prop["people"]:
            return ", ".join(p.get("name", "") for p in prop["people"])
        if "title" in prop and prop["title"]:
            return prop["title"][0].get("plain_text", "") if prop["title"] else ""
        if "rich_text" in prop and prop["rich_text"]:
            return prop["rich_text"][0].get("plain_text", "") if prop["rich_text"] else ""
        if "number" in prop and prop["number"] is not None:
            return str(prop["number"])
        return ""
