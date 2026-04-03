import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
import structlog

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData

logger = structlog.get_logger()


class SlackAdapter(ConnectorAdapter):
    """Connector for Slack — messages, threads, and channel info."""

    adapter_type = "slack"

    def __init__(self, bot_token: str = "") -> None:
        self.bot_token = bot_token
        self.client = AsyncWebClient(token=bot_token)

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Slack API.

        Args:
            query: {"type": "messages|channels|thread", "channel": "...", "thread_ts": "..."}
        """
        query_type = query.get("type", "messages")

        try:
            if query_type == "messages":
                channel_id = query.get("channel")
                if not channel_id: raise ValueError("Channel ID is required for fetching messages.")
                response = await self.client.conversations_history(channel=channel_id)
                return {"ok": True, "type": "messages", "channel": channel_id, "messages": response.get("messages", [])}
            elif query_type == "channels":
                response = await self.client.conversations_list(types="public_channel,private_channel")
                return {"ok": True, "type": "channels", "channels": response.get("channels", [])}
            elif query_type == "thread":
                channel_id = query.get("channel")
                thread_ts = query.get("thread_ts")
                if not channel_id or not thread_ts: raise ValueError("Channel ID and thread_ts are required for fetching a thread.")
                response = await self.client.conversations_replies(channel=channel_id, ts=thread_ts)
                return {"ok": True, "type": "thread", "channel": channel_id, "messages": response.get("messages", [])}
            else:
                raise ValueError(f"Unsupported Slack query type: {query_type}")
        except SlackApiError as e:
            logger.error("slack_api_error", method=query_type, error=str(e))
            raise

    async def health_check(self) -> ConnectorHealthResult:
        """Check Slack API connectivity by calling auth.test."""
        start = time.monotonic()
        try:
            response = await self.client.auth_test()
            if response["ok"]:
                status = "healthy"
            else:
                status = "unhealthy"
                logger.error("slack_health_check_failed", error=response.get("error"))
        except SlackApiError as e:
            status = "unhealthy"
            logger.error("slack_health_check_error", error=str(e))
        latency = (time.monotonic() - start) * 1000

        return ConnectorHealthResult(
            status=status,
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
            user = msg.get("user_name", msg.get("user", "unknown")) # Slack API might return user ID, need to fetch user info if desired
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
            members = ch.get("num_members", 0) # Slack API might not directly provide num_members in conversations_list
            topic = ch.get("topic", {}).get("value", "—")
            lines.append(f"| #{name} | {members} | {topic} |")

        return NormalizedData(
            source="slack",
            data_type="channels",
            content="\n".join(lines),
            metadata={"channel_count": len(channels)},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
