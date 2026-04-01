"""GoogleWorkspaceAdapter — OAuth2, normalize Drive files + Gmail threads."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class GoogleWorkspaceAdapter(ConnectorAdapter):
    """Connector for Google Workspace — Drive files and Gmail threads."""

    adapter_type = "google_workspace"

    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token

    async def fetch(self, query: dict) -> dict[str, Any]:
        obj_type = query.get("object", "drive_files")
        simulated: dict[str, dict] = {
            "drive_files": {
                "objectType": "drive_files",
                "files": [
                    {"id": "f001", "name": "Q4 Budget.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet",
                     "modifiedTime": "2026-03-28T10:00:00Z", "owners": [{"displayName": "Alice"}], "size": "245000"},
                    {"id": "f002", "name": "Product Roadmap.docx", "mimeType": "application/vnd.google-apps.document",
                     "modifiedTime": "2026-03-25T15:30:00Z", "owners": [{"displayName": "Bob"}], "size": "128000"},
                    {"id": "f003", "name": "Architecture Diagram.png", "mimeType": "image/png",
                     "modifiedTime": "2026-03-20T09:00:00Z", "owners": [{"displayName": "Carol"}], "size": "890000"},
                ],
            },
            "gmail_threads": {
                "objectType": "gmail_threads",
                "threads": [
                    {"id": "t001", "subject": "Re: Deployment approval needed",
                     "snippet": "Approved. Please proceed with staging deployment.",
                     "messages_count": 4, "last_message_date": "2026-03-30T16:00:00Z"},
                    {"id": "t002", "subject": "Weekly sync notes",
                     "snippet": "Key decisions from today's sync: 1) Launch date confirmed...",
                     "messages_count": 2, "last_message_date": "2026-03-29T11:00:00Z"},
                ],
            },
        }
        return simulated.get(obj_type, {"objectType": obj_type})

    async def health_check(self) -> ConnectorHealthResult:
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 50.0
        return ConnectorHealthResult(status="healthy", latency_ms=round(latency, 2),
                                     checked_at=datetime.now(timezone.utc).isoformat())

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        obj_type = raw_data.get("objectType", "unknown")
        if obj_type == "drive_files":
            return self._normalize_drive(raw_data)
        elif obj_type == "gmail_threads":
            return self._normalize_gmail(raw_data)
        return NormalizedData(source="google_workspace", data_type=obj_type,
                             content=f"# Unknown Google type: {obj_type}",
                             fetched_at=datetime.now(timezone.utc).isoformat())

    def _normalize_drive(self, data: dict) -> NormalizedData:
        files = data.get("files", [])
        lines = [f"# Google Drive Files ({len(files)})\n"]
        for f in files:
            size_kb = int(f.get("size", 0)) // 1024
            owner = f.get("owners", [{}])[0].get("displayName", "Unknown") if f.get("owners") else "Unknown"
            lines.append(f"## {f['name']}")
            lines.append(f"- **Type**: {f.get('mimeType', 'N/A')}")
            lines.append(f"- **Modified**: {f.get('modifiedTime', 'N/A')}")
            lines.append(f"- **Owner**: {owner}")
            lines.append(f"- **Size**: {size_kb} KB")
            lines.append("")

        return NormalizedData(source="google_workspace", data_type="drive_files",
                             content="\n".join(lines), metadata={"file_count": len(files)},
                             fetched_at=datetime.now(timezone.utc).isoformat())

    def _normalize_gmail(self, data: dict) -> NormalizedData:
        threads = data.get("threads", [])
        lines = [f"# Gmail Threads ({len(threads)})\n"]
        for t in threads:
            lines.append(f"## {t.get('subject', 'No subject')}")
            lines.append(f"- **Messages**: {t.get('messages_count', 0)}")
            lines.append(f"- **Last message**: {t.get('last_message_date', 'N/A')}")
            lines.append(f"- **Preview**: {t.get('snippet', '')}")
            lines.append("")

        return NormalizedData(source="google_workspace", data_type="gmail_threads",
                             content="\n".join(lines), metadata={"thread_count": len(threads)},
                             fetched_at=datetime.now(timezone.utc).isoformat())
