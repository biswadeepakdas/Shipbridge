"""JMESPathExecutor — applies NormalizationRule payload_map to raw event payloads.

Maps raw Composio/webhook payloads to normalized AgentEvent fields using
JMESPath expressions (via the jmespath library).
"""

from datetime import datetime, timezone
from typing import Any

import jmespath
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


def execute_rule(rule: NormalizationRuleEntry, raw_payload: dict) -> NormalizedEvent | None:
    """Apply a NormalizationRule's payload_map to a raw event payload.

    The payload_map is a dict of {output_field: source_path_or_literal}.
    - If value contains "." or "[", it's resolved via jmespath.search from raw_payload.
    - Otherwise, it's treated as a literal string value.

    Returns None if the rule cannot produce a valid event_type.
    """
    normalized_payload: dict = {}

    for output_field, source_expr in rule.payload_map.items():
        if isinstance(source_expr, str) and ("." in source_expr or "[" in source_expr):
            # Only resolve as JMESPath if the root key exists in the payload
            root_key = source_expr.split(".")[0].split("[")[0]
            if root_key in raw_payload:
                resolved = jmespath.search(source_expr, raw_payload)
                normalized_payload[output_field] = resolved
            else:
                # Root key not in payload — treat as literal value
                normalized_payload[output_field] = source_expr
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
