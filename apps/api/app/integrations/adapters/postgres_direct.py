"""PostgresDirectAdapter — Connection string, normalize query results."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class PostgresDirectAdapter(ConnectorAdapter):
    """Connector for direct Postgres queries — normalize results as markdown tables."""

    adapter_type = "postgres"

    def __init__(self, connection_string: str = "") -> None:
        self.connection_string = connection_string

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Simulate a Postgres query. In production, would execute real SQL via asyncpg."""
        sql = query.get("sql", "SELECT 1")
        simulated = {
            "objectType": "query_result",
            "sql": sql,
            "columns": ["id", "name", "status", "created_at"],
            "rows": [
                [1, "Agent Alpha", "active", "2026-03-01"],
                [2, "Agent Beta", "paused", "2026-03-15"],
                [3, "Agent Gamma", "active", "2026-03-20"],
            ],
            "row_count": 3,
            "execution_time_ms": 12.5,
        }
        return simulated

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 8.0
        return ConnectorHealthResult(status="healthy", latency_ms=round(latency, 2),
                                     checked_at=datetime.now(timezone.utc).isoformat())

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        columns = raw_data.get("columns", [])
        rows = raw_data.get("rows", [])
        row_count = raw_data.get("row_count", len(rows))
        exec_time = raw_data.get("execution_time_ms", 0)

        lines = [f"# Query Result ({row_count} rows, {exec_time}ms)\n"]

        if columns and rows:
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(str(v) for v in row) + " |")

        lines.append(f"\n*SQL*: `{raw_data.get('sql', 'N/A')}`")

        return NormalizedData(source="postgres", data_type="query_result",
                             content="\n".join(lines),
                             metadata={"row_count": row_count, "execution_time_ms": exec_time},
                             fetched_at=datetime.now(timezone.utc).isoformat())
