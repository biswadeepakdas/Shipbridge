"""AgentTriggerSubscriptionEngine — matches events against subscriptions with JMESPath filters.

Flow: NormalizedEvent → match against active subscriptions → debounce check → trigger agent
"""

import time
from datetime import datetime, timezone

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class Subscription(BaseModel):
    """An event subscription definition."""

    id: str
    tenant_id: str
    name: str
    event_type: str
    filter_expression: str | None = None  # Simplified JMESPath-like filter
    agent_id: str
    debounce_seconds: int = 0
    is_active: bool = True


class SubscriptionMatch(BaseModel):
    """A matched subscription for a triggered event."""

    subscription_id: str
    subscription_name: str
    agent_id: str
    event_type: str
    debounced: bool = False
    triggered_at: str


class SubscriptionMatchResult(BaseModel):
    """Result of matching an event against all subscriptions."""

    event_type: str
    matches: list[SubscriptionMatch]
    total_subscriptions_checked: int
    total_matched: int
    total_debounced: int


def _evaluate_filter(filter_expr: str, payload: dict) -> bool:
    """Evaluate a simplified filter expression against a payload.

    Supports:
    - "payload.field == value"
    - "payload.field > N"
    - "payload.field contains text"
    - "payload.field exists"

    In production, uses full JMESPath evaluation.
    """
    if not filter_expr or not filter_expr.strip():
        return True  # No filter = always match

    expr = filter_expr.strip()

    # Handle "exists" checks
    if expr.endswith(" exists"):
        field_path = expr.replace(" exists", "").strip()
        return _resolve_field(payload, field_path) is not None

    # Handle comparison operators
    for op in (" == ", " != ", " > ", " >= ", " < ", " <= ", " contains "):
        if op in expr:
            field_path, value_str = expr.split(op, 1)
            field_path = field_path.strip()
            value_str = value_str.strip().strip("'\"").strip("`")

            field_value = _resolve_field(payload, field_path)
            if field_value is None:
                return False

            if op.strip() == "contains":
                return str(value_str).lower() in str(field_value).lower()

            # Numeric comparison
            try:
                num_field = float(field_value)
                num_value = float(value_str)
                if op.strip() == "==":
                    return num_field == num_value
                elif op.strip() == "!=":
                    return num_field != num_value
                elif op.strip() == ">":
                    return num_field > num_value
                elif op.strip() == ">=":
                    return num_field >= num_value
                elif op.strip() == "<":
                    return num_field < num_value
                elif op.strip() == "<=":
                    return num_field <= num_value
            except (ValueError, TypeError):
                # String comparison
                if op.strip() == "==":
                    return str(field_value) == value_str
                elif op.strip() == "!=":
                    return str(field_value) != value_str

    # Fallback: treat as truthy check
    return True


def _resolve_field(data: dict, path: str) -> object:
    """Resolve a dot-notation field path in a nested dict."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


class SubscriptionEngine:
    """Matches events against subscriptions with filter evaluation and debounce."""

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._last_triggered: dict[str, float] = {}  # sub_id → timestamp

    def register(self, subscription: Subscription) -> None:
        """Register a subscription."""
        self._subscriptions.append(subscription)

    def remove(self, subscription_id: str) -> bool:
        """Remove a subscription by ID."""
        before = len(self._subscriptions)
        self._subscriptions = [s for s in self._subscriptions if s.id != subscription_id]
        return len(self._subscriptions) < before

    def list_subscriptions(self, tenant_id: str | None = None) -> list[Subscription]:
        """List subscriptions, optionally filtered by tenant."""
        subs = [s for s in self._subscriptions if s.is_active]
        if tenant_id:
            subs = [s for s in subs if s.tenant_id == tenant_id]
        return subs

    def match_event(
        self,
        event_type: str,
        payload: dict,
        tenant_id: str | None = None,
    ) -> SubscriptionMatchResult:
        """Match an event against all active subscriptions for a tenant."""
        candidates = self.list_subscriptions(tenant_id)
        matches: list[SubscriptionMatch] = []
        debounced_count = 0

        for sub in candidates:
            # Event type must match
            if sub.event_type != event_type and sub.event_type != "*":
                continue

            # Evaluate filter expression
            if sub.filter_expression and not _evaluate_filter(sub.filter_expression, payload):
                continue

            # Debounce check
            now = time.monotonic()
            last = self._last_triggered.get(sub.id, 0)
            if sub.debounce_seconds > 0 and (now - last) < sub.debounce_seconds:
                matches.append(SubscriptionMatch(
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    agent_id=sub.agent_id,
                    event_type=event_type,
                    debounced=True,
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                ))
                debounced_count += 1
                continue

            # Match!
            self._last_triggered[sub.id] = now
            matches.append(SubscriptionMatch(
                subscription_id=sub.id,
                subscription_name=sub.name,
                agent_id=sub.agent_id,
                event_type=event_type,
                debounced=False,
                triggered_at=datetime.now(timezone.utc).isoformat(),
            ))

        active_matches = [m for m in matches if not m.debounced]
        if active_matches:
            logger.info("subscriptions_matched", event_type=event_type,
                       matched=len(active_matches), debounced=debounced_count)

        return SubscriptionMatchResult(
            event_type=event_type,
            matches=matches,
            total_subscriptions_checked=len(candidates),
            total_matched=len(active_matches),
            total_debounced=debounced_count,
        )

    def clear(self) -> None:
        self._subscriptions.clear()
        self._last_triggered.clear()


# Singleton
subscription_engine = SubscriptionEngine()
