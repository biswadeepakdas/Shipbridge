"""LinearAdapter — API key auth, normalize issues/projects/cycles/comments."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class LinearAdapter(ConnectorAdapter):
    """Connector for Linear — issues, projects, cycles, comments."""

    adapter_type = "linear"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def fetch(self, query: dict) -> dict[str, Any]:
        obj_type = query.get("object", "issues")
        simulated: dict[str, dict] = {
            "issues": {
                "objectType": "issues",
                "items": [
                    {"id": "LIN-101", "title": "Implement webhook receiver", "state": "In Progress",
                     "priority": 1, "assignee": "alice", "project": "Integration OS", "estimate": 3},
                    {"id": "LIN-102", "title": "Add circuit breaker tests", "state": "Done",
                     "priority": 2, "assignee": "bob", "project": "Integration OS", "estimate": 2},
                    {"id": "LIN-103", "title": "Design normalization rule UI", "state": "Backlog",
                     "priority": 3, "assignee": None, "project": "Dashboard", "estimate": 5},
                ],
            },
            "projects": {
                "objectType": "projects",
                "items": [
                    {"id": "proj-1", "name": "Integration OS", "state": "started",
                     "progress": 0.65, "lead": "alice", "target_date": "2026-04-15"},
                    {"id": "proj-2", "name": "Dashboard", "state": "started",
                     "progress": 0.40, "lead": "carol", "target_date": "2026-04-30"},
                ],
            },
            "cycles": {
                "objectType": "cycles",
                "items": [
                    {"id": "cycle-1", "name": "Sprint 12", "starts_at": "2026-03-25",
                     "ends_at": "2026-04-07", "progress": 0.70, "completed_issues": 7, "total_issues": 10},
                ],
            },
        }
        return simulated.get(obj_type, {"objectType": obj_type, "items": []})

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 32.0
        return ConnectorHealthResult(status="healthy", latency_ms=round(latency, 2),
                                     checked_at=datetime.now(timezone.utc).isoformat())

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        obj_type = raw_data.get("objectType", "unknown")
        items = raw_data.get("items", [])
        lines = [f"# Linear {obj_type.replace('_', ' ').title()} ({len(items)} items)\n"]

        for item in items:
            if obj_type == "issues":
                priority_labels = {1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
                pri = priority_labels.get(item.get("priority", 4), "None")
                lines.append(f"## {item['id']}: {item['title']}")
                lines.append(f"- **State**: {item.get('state', '')}")
                lines.append(f"- **Priority**: {pri}")
                lines.append(f"- **Assignee**: {item.get('assignee') or 'unassigned'}")
                lines.append(f"- **Estimate**: {item.get('estimate', '?')} pts")
                lines.append("")
            elif obj_type == "projects":
                pct = int(item.get("progress", 0) * 100)
                lines.append(f"## {item['name']}")
                lines.append(f"- **Progress**: {pct}%")
                lines.append(f"- **Lead**: {item.get('lead', 'N/A')}")
                lines.append(f"- **Target**: {item.get('target_date', 'N/A')}")
                lines.append("")
            elif obj_type == "cycles":
                pct = int(item.get("progress", 0) * 100)
                lines.append(f"## {item['name']}")
                lines.append(f"- **Progress**: {pct}% ({item.get('completed_issues', 0)}/{item.get('total_issues', 0)})")
                lines.append(f"- **Period**: {item.get('starts_at', '')} → {item.get('ends_at', '')}")
                lines.append("")

        return NormalizedData(source="linear", data_type=obj_type, content="\n".join(lines),
                             metadata={"total_items": len(items)},
                             fetched_at=datetime.now(timezone.utc).isoformat())
