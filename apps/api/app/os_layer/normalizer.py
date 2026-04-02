"""Event normalizer — processes raw webhook payloads through the rule pipeline.

Flow: Raw payload → RuleRegistry lookup → JMESPathExecutor → NormalizedEvent
If no rule found → UnknownEventQueue for offline rule generation.
"""

import uuid
from datetime import datetime, timezone

import structlog

from app.os_layer.jmespath_executor import NormalizedEvent, execute_rule
from app.os_layer.rule_registry import rule_registry
from app.os_layer.unknown_event_queue import UnknownEvent, unknown_event_queue

logger = structlog.get_logger()


class NormalizationResult:
    """Result of processing a raw event through the normalization pipeline."""

    def __init__(
        self,
        normalized: NormalizedEvent | None = None,
        queued_as_unknown: bool = False,
        error: str | None = None,
    ) -> None:
        self.normalized = normalized
        self.queued_as_unknown = queued_as_unknown
        self.error = error

    @property
    def success(self) -> bool:
        return self.normalized is not None


def normalize_event(
    app: str,
    trigger: str,
    raw_payload: dict,
    tenant_id: str | None = None,
) -> NormalizationResult:
    """Process a raw event payload through the normalization pipeline.

    1. Look up active NormalizationRule by (app, trigger)
    2. If found → execute JMESPath payload_map → return NormalizedEvent
    3. If not found → queue to UnknownEventQueue for offline rule generation
    """
    # Step 1: Rule lookup
    rule = rule_registry.lookup(app, trigger)

    if rule:
        # Step 2: Execute rule
        try:
            normalized = execute_rule(rule, raw_payload)
            if normalized:
                logger.info("event_normalized", app=app, trigger=trigger,
                           event_type=normalized.event_type, rule_id=rule.rule_id)
                return NormalizationResult(normalized=normalized)
            else:
                logger.warning("rule_produced_no_event", app=app, trigger=trigger, rule_id=rule.rule_id)
                return NormalizationResult(error="Rule did not produce a valid event_type")
        except Exception as e:
            logger.error("normalization_failed", app=app, trigger=trigger, error=str(e))
            return NormalizationResult(error=str(e))

    # Step 3: No rule found — queue as unknown
    unknown = UnknownEvent(
        id=str(uuid.uuid4()),
        app=app,
        trigger=trigger,
        raw_payload=raw_payload,
        received_at=datetime.now(timezone.utc).isoformat(),
        tenant_id=tenant_id,
    )
    unknown_event_queue.enqueue(unknown)
    logger.info("unknown_event_queued", app=app, trigger=trigger, queue_size=unknown_event_queue.size)

    return NormalizationResult(queued_as_unknown=True)
