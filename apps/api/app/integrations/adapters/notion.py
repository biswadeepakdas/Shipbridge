import time
from datetime import datetime, timezone
from typing import Any, Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData
from app.config import get_settings

class NotionAdapter(ConnectorAdapter):
    """Connector for Notion — pages, databases, and blocks."""

    adapter_type = "notion"

    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token
        self.notion_client: Optional[Client] = None

    async def _connect(self) -> None:
        settings = get_settings()
        if not self.notion_client:
            token = self.access_token or settings.notion_api_key
            if not token:
                raise ConnectionError("Notion API key or access token is missing.")
            self.notion_client = Client(auth=token)

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Notion API.

        Args:
            query: {"type": "page|database|search", "id": "...", "filters": {...}, "query": "..."}
        """
        await self._connect()
        if not self.notion_client:
            raise ConnectionError("Notion client not initialized.")

        query_type = query.get("type", "search")
        object_id = query.get("id")
        filters = query.get("filters", {})
        search_query = query.get("query")

        try:
            if query_type == "page" and object_id:
                response = self.notion_client.pages.retrieve(page_id=object_id)
            elif query_type == "database" and object_id:
                response = self.notion_client.databases.query(database_id=object_id, filter=filters)
            elif query_type == "search" and search_query:
                response = self.notion_client.search(query=search_query, filter=filters)
            else:
                raise ValueError(f"Invalid Notion query type or missing ID/query: {query_type}")
            
            # Add objectType for normalization helper
            if "object" in response:
                response["objectType"] = response["object"]
            elif "results" in response and response["results"] and "object" in response["results"][0]:
                response["objectType"] = response["results"][0]["object"]
            else:
                response["objectType"] = query_type

            return response
        except APIResponseError as e:
            raise RuntimeError(f"Notion API call failed: {e.code} - {e.message}") from e

    async def health_check(self) -> ConnectorHealthResult:
        """Check Notion API connectivity."""
        start = time.monotonic()
        status = "unhealthy"
        error_message = None
        try:
            await self._connect()
            if self.notion_client:
                # Attempt a simple API call to verify connectivity (e.g., list users)
                # Note: listing users requires 'read_user' capability
                # A simpler check might be to just retrieve a non-existent block/page to test auth
                self.notion_client.users.list()
                status = "healthy"
        except APIResponseError as e:
            error_message = f"Notion API error: {e.code} - {e.message}"
        except Exception as e:
            error_message = str(e)

        latency = (time.monotonic() - start) * 1000

        return ConnectorHealthResult(
            status=status,
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
            error_message=error_message
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform Notion API response into agent-friendly markdown."""
        obj_type = raw_data.get("objectType", "unknown")

        if obj_type == "page":
            return self._normalize_page(raw_data)
        elif obj_type == "database":
            return self._normalize_database_query_results(raw_data)
        elif obj_type == "list" or obj_type == "search": # Search results are typically a list
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
        lines.append(f"- **Created**: {data.get("created_time", "N/A")}")
        lines.append(f"- **Last edited**: {data.get("last_edited_time", "N/A")}")

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

    def _normalize_database_query_results(self, data: dict) -> NormalizedData:
        """Normalize Notion database query results."""
        results = data.get("results", [])
        
        # Try to get database title from the first result if available, or from query context if passed
        db_title = "Untitled Database"
        if results and "parent" in results[0] and "database_id" in results[0]["parent"]:
            # This is tricky as database title is not directly in query results
            # For now, we'll use a generic title or try to infer from properties
            pass # Will need to fetch database metadata separately for a proper title

        lines = [f"# {db_title} ({len(results)} rows)\n"]
        if results:
            # Attempt to get property names for header
            first_props = results[0].get("properties", {})
            headers = ["Name"] + [k for k in first_props.keys() if k != "Name"]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|---" * len(headers) + "|")

            for row in results:
                props = row.get("properties", {})
                row_values = []
                for header in headers:
                    value = self._extract_property_value(props.get(header, {}))
                    row_values.append(value if value else "—")
                lines.append("| " + " | ".join(row_values) + " |")

        return NormalizedData(
            source="notion",
            data_type="database",
            content="\n".join(lines),
            metadata={"row_count": len(results)},
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
                lines.append(f"- **Page**: {title} (id: {item.get("id", "")})")
            elif obj == "database":
                # Database title is not directly in search results, need to retrieve separately
                lines.append(f"- **Database**: ID: {item.get("id", "")} (title not available)")
            elif obj == "block":
                lines.append(f"- **Block**: ID: {item.get("id", "")} (content not directly available)")

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
        if "title" in prop and prop["title"]:
            return prop["title"][0].get("plain_text", "Untitled") if prop["title"] else "Untitled"
        return "Untitled"

    @staticmethod
    def _extract_property_value(prop: dict) -> str:
        """Extract display value from a Notion property."""
        if "select" in prop and prop["select"]:
            return prop["select"].get("name", "")
        if "multi_select" in prop and prop["multi_select"]:
            return ", ".join(s.get("name", "") for s in prop["multi_select"])
        if "people" in prop and prop["people"]:
            return ", ".join(p.get("name", "") for p in prop["people"])
        if "title" in prop and prop["title"]:
            return prop["title"][0].get("plain_text", "") if prop["title"] else ""
        if "rich_text" in prop and prop["rich_text"]:
            return prop["rich_text"][0].get("plain_text", "") if prop["rich_text"] else ""
        if "number" in prop and prop["number"] is not None:
            return str(prop["number"])
        if "url" in prop and prop["url"]:
            return prop["url"]
        if "email" in prop and prop["email"]:
            return prop["email"]
        if "phone_number" in prop and prop["phone_number"]:
            return prop["phone_number"]
        if "checkbox" in prop and prop["checkbox"] is not None:
            return "Yes" if prop["checkbox"] else "No"
        if "date" in prop and prop["date"] and "start" in prop["date"]:
            return prop["date"]["start"]
        if "files" in prop and prop["files"]:
            return ", ".join(f.get("name", "") for f in prop["files"])
        if "formula" in prop and prop["formula"] and "string" in prop["formula"]:
            return prop["formula"]["string"]
        if "relation" in prop and prop["relation"]:
            return f"{len(prop["relation"])} related items"
        if "rollup" in prop and prop["rollup"] and "number" in prop["rollup"]:
            return str(prop["rollup"]["number"])
        if "created_time" in prop and prop["created_time"]:
            return prop["created_time"]
        if "last_edited_time" in prop and prop["last_edited_time"]:
            return prop["last_edited_time"]
        
        return ""
