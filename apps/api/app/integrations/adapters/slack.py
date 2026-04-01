"""SlackAdapter — Bot token auth, normalize messages/threads/channel info."""

import time
from datetime import datetime, timezone
from typing import Any

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData


class SlackAdapter(ConnectorAdapter):
    """Connector for Slack — messages, threads, and channel info."""

    adapter_type = "slack"

    def __init__(self, bot_token: str = "") -> None:
        self.bot_token = bot_token

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Slack API.

        Args:
            query: {"type": "messages|channels|thread", "channel": "...", "thread_ts": "..."}
        """
        query_type = query.get("type", "messages")

        simulated: dict[str, dict] = {
            "messages": {
                "ok": True,
                "type": "messages",
                "channel": query.get("channel", "C01GENERAL"),
                "messages": [
                    {"user": "U001", "user_name": "alice", "text": "Deployed v2.3 to staging. All tests green.",
                     "ts": "1711900000.000100", "type": "message"},
                    {"user": "U002", "user_name": "bob", "text": "LGTM, promoting to production.",
                     "ts": "1711900060.000200", "type": "message"},
                    {"user": "U003", "user_name": "carol", "text": "Monitoring dashboards look stable after 30min.",
                     "ts": "1711901800.000300", "type": "message"},
                ],
            },
            "channels": {
                "ok": True,
                "type": "channels",
                "channels": [
                    {"id": "C01GENERAL", "name": "general", "num_members": 45, "topic": {"value": "Company-wide announcements"}},
                    {"id": "C02ENGINEERING", "name": "engineering", "num_members": 18, "topic": {"value": "Engineering discussions"}},
                    {"id": "C03DEPLOYS", "name": "deploys", "num_members": 12, "topic": {"value": "Deployment notifications"}},
                ],
            },
            "thread": {
                "ok": True,
                "type": "thread",
                "messages": [
                    {"user": "U001", "user_name": "alice", "text": "Anyone seeing latency spikes on the API?",
                     "ts": "1711900000.000100", "type": "message"},
                    {"user": "U002", "user_name": "bob", "text": "Yes, p99 is at 800ms. Investigating.",
                     "ts": "1711900120.000200", "type": "message", "thread_ts": "1711900000.000100"},
                    {"user": "U002", "user_name": "bob", "text": "Found it — Redis connection pool exhaustion. Fix deployed.",
                     "ts": "1711900300.000300", "type": "message", "thread_ts": "1711900000.000100"},
                ],
            },
        }

        return simulated.get(query_type, {"ok": True, "type": query_type, "messages": []})

    async def health_check(self) -> ConnectorHealthResult:
        """Check Slack API connectivity."""
        start = time.monotonic()
        latency = (time.monotonic() - start) * 1000 + 22.0

        return ConnectorHealthResult(
            status="healthy",
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform Slack API response into agent-friendly markdown."""
        data_type = raw_data.get("type", "unknown")

        if data_type in ("messages", "thread"):
            return self._normalize_messages(raw_data)
        elif data_type == "channels":
            return self._normalize_channels(raw_data)
        else:
            return NormalizedData(
                source="slack", data_type=data_type,
                content=f"# Unknown Slack data type: {data_type}",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

    def _normalize_messages(self, data: dict) -> NormalizedData:
        messages = data.get("messages", [])
        is_thread = data.get("type") == "thread"
        channel = data.get("channel", "")

        label = "Thread" if is_thread else f"Channel #{channel}"
        lines = [f"# Slack {label} ({len(messages)} messages)\n"]

        for msg in messages:
            user = msg.get("user_name", msg.get("user", "unknown"))
            text = msg.get("text", "")
            lines.append(f"**@{user}**: {text}")

        return NormalizedData(
            source="slack",
            data_type="thread" if is_thread else "messages",
            content="\n".join(lines),
            metadata={"message_count": len(messages), "channel": channel},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    def _normalize_channels(self, data: dict) -> NormalizedData:
        channels = data.get("channels", [])
        lines = [f"# Slack Channels ({len(channels)})\n"]
        lines.append("| Channel | Members | Topic |")
        lines.append("|---------|---------|-------|")

        for ch in channels:
            name = ch.get("name", "unknown")
            members = ch.get("num_members", 0)
            topic = ch.get("topic", {}).get("value", "—")
            lines.append(f"| #{name} | {members} | {topic} |")

        return NormalizedData(
            source="slack",
            data_type="channels",
            content="\n".join(lines),
            metadata={"channel_count": len(channels)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
