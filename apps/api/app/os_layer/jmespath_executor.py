"""JMESPathExecutor — applies NormalizationRule payload_map to raw event payloads.

Maps raw Composio/webhook payloads to normalized AgentEvent fields using
JMESPath-like dot-notation expressions.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.os_layer.rule_registry import NormalizationRuleEntry


class NormalizedEvent(BaseModel):
    """Output of the JMESPath executor — ready to become an AgentEvent."""

    event_type: str
    source: str
    payload: dict
    rule_id: str
    rule_version: int
    normalized_at: str


def _resolve_path(data: dict, path: str) -> Any:
    """Resolve a dot-notation path against a nested dict.

    Supports paths like "payload.Amount", "data.items[0].name".
    Falls back to None if path doesn't resolve.
    """
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if current is None:
            return None
        # Handle array index notation like "items[0]"
        if "[" in part and "]" in part:
            key, idx_str = part.split("[", 1)
            idx = int(idx_str.rstrip("]"))
            current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, list) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def execute_rule(rule: NormalizationRuleEntry, raw_payload: dict) -> NormalizedEvent | None:
    """Apply a NormalizationRule's payload_map to a raw event payload.

    The payload_map is a dict of {output_field: source_path_or_literal}.
    - If value starts with "payload." or "data.", it's resolved from raw_payload.
    - Otherwise, it's treated as a literal string value.

    Returns None if the rule cannot produce a valid event_type.
    """
    normalized_payload: dict = {}

    for output_field, source_expr in rule.payload_map.items():
        if isinstance(source_expr, str) and ("." in source_expr and source_expr.split(".")[0] in ("payload", "data", "raw")):
            resolved = _resolve_path(raw_payload, source_expr)
            normalized_payload[output_field] = resolved
        else:
            # Literal value
            normalized_payload[output_field] = source_expr

    event_type = normalized_payload.pop("event_type", None)
    if not event_type:
        return None

    return NormalizedEvent(
        event_type=str(event_type),
        source=rule.app,
        payload=normalized_payload,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        normalized_at=datetime.now(timezone.utc).isoformat(),
    )
