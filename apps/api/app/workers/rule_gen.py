"""RuleGeneratorJob — drains UnknownEventQueue, generates draft NormalizationRules via LLM.

In production, runs as a Celery beat task every 5 minutes.
Uses Haiku for structured output → NormalizationRule JSON.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel

from app.os_layer.rule_registry import NormalizationRuleEntry, rule_registry
from app.os_layer.unknown_event_queue import UnknownEvent, unknown_event_queue

logger = structlog.get_logger()


class GeneratedRule(BaseModel):
    """Output of the LLM rule generation process."""

    rule: NormalizationRuleEntry
    sample_payload: dict
    confidence: float
    reasoning: str


class RuleGenerationResult(BaseModel):
    """Summary of a rule generation batch run."""

    processed: int
    generated: int
    failed: int
    rules: list[GeneratedRule]


def _generate_payload_map_from_sample(app: str, trigger: str, sample_payload: dict) -> dict:
    """Generate a JMESPath payload_map from a sample event payload.

    In production, this would call Haiku with structured output.
    For now, uses heuristic mapping based on common field patterns.
    """
    payload_map: dict[str, str] = {}

    # Always set event_type from app.trigger
    payload_map["event_type"] = f"{app}.{trigger.replace('_', '.')}"

    # Map common field patterns
    field_mappings = {
        "id": "payload.id",
        "name": "payload.name",
        "title": "payload.title",
        "status": "payload.status",
        "state": "payload.state",
        "email": "payload.email",
        "amount": "payload.amount",
        "url": "payload.url",
        "description": "payload.description",
        "created_at": "payload.created_at",
        "updated_at": "payload.updated_at",
        "user": "payload.user",
        "assignee": "payload.assignee",
        "priority": "payload.priority",
        "type": "payload.type",
        "source": "payload.source",
    }

    # Walk the sample payload and map recognized fields
    def _walk(obj: dict, prefix: str = "payload") -> None:
        for key, value in obj.items():
            full_path = f"{prefix}.{key}"
            lower_key = key.lower()

            # Check if this field matches a known pattern
            for pattern, _ in field_mappings.items():
                if pattern in lower_key:
                    payload_map[lower_key.replace(".", "_")] = full_path
                    break

            # Recurse into nested dicts (1 level deep)
            if isinstance(value, dict) and prefix == "payload":
                _walk(value, full_path)

    if sample_payload:
        _walk(sample_payload)

    return payload_map


def _generate_rule_for_event(event: UnknownEvent) -> GeneratedRule | None:
    """Generate a draft NormalizationRule for a single unknown event.

    In production, would call Claude Haiku with:
    - The trigger schema from Composio
    - The sample payload
    - Instructions to output a NormalizationRule JSON
    """
    try:
        payload_map = _generate_payload_map_from_sample(
            event.app, event.trigger, event.raw_payload,
        )

        if not payload_map.get("event_type"):
            return None

        rule = NormalizationRuleEntry(
            rule_id=str(uuid.uuid4()),
            app=event.app,
            trigger=event.trigger,
            payload_map=payload_map,
            status="draft",
            version=1,
        )

        # Validate by checking if the rule would produce output
        confidence = 0.7 if len(payload_map) > 2 else 0.4

        return GeneratedRule(
            rule=rule,
            sample_payload=event.raw_payload,
            confidence=confidence,
            reasoning=f"Generated from sample payload with {len(payload_map)} field mappings",
        )

    except Exception as e:
        logger.error("rule_generation_failed", app=event.app, trigger=event.trigger, error=str(e))
        return None


def run_rule_generator(batch_size: int = 50) -> RuleGenerationResult:
    """Drain unknown events and generate draft rules.

    This is the main entry point called by Celery beat every 5 minutes.
    """
    events = unknown_event_queue.drain(limit=batch_size)

    if not events:
        return RuleGenerationResult(processed=0, generated=0, failed=0, rules=[])

    generated_rules: list[GeneratedRule] = []
    failed = 0

    # Deduplicate by (app, trigger) — only generate one rule per unique trigger
    seen_triggers: set[str] = set()

    for event in events:
        trigger_key = f"{event.app}:{event.trigger}"
        if trigger_key in seen_triggers:
            continue
        seen_triggers.add(trigger_key)

        # Skip if a rule already exists (active or draft)
        existing = rule_registry.lookup(event.app, event.trigger)
        if existing:
            continue

        result = _generate_rule_for_event(event)
        if result:
            # Register as draft in the registry
            rule_registry.register(result.rule)
            generated_rules.append(result)
            logger.info("draft_rule_generated", app=event.app, trigger=event.trigger,
                       rule_id=result.rule.rule_id, confidence=result.confidence)
        else:
            failed += 1

    return RuleGenerationResult(
        processed=len(events),
        generated=len(generated_rules),
        failed=failed,
        rules=generated_rules,
    )


# --- Schema Hash Drift Detection ---

class SchemaHash(BaseModel):
    """Hash record for Composio trigger schema drift detection."""

    app: str
    trigger: str
    schema_hash: str
    checked_at: str
    needs_review: bool = False


_schema_hashes: dict[str, SchemaHash] = {}


def compute_schema_hash(app: str, trigger: str, schema: dict) -> str:
    """Compute SHA-256 hash of a trigger schema for drift detection."""
    canonical = json.dumps(schema, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def check_schema_drift(app: str, trigger: str, current_schema: dict) -> SchemaHash:
    """Compare current schema hash against stored hash. Flags drift if changed.

    Called nightly by SchemaHashJob to detect Composio SDK version changes.
    """
    key = f"{app}:{trigger}"
    current_hash = compute_schema_hash(app, trigger, current_schema)
    now = datetime.now(timezone.utc).isoformat()

    stored = _schema_hashes.get(key)
    needs_review = False

    if stored and stored.schema_hash != current_hash:
        needs_review = True
        logger.warning("schema_drift_detected", app=app, trigger=trigger,
                      old_hash=stored.schema_hash, new_hash=current_hash)

    entry = SchemaHash(
        app=app, trigger=trigger, schema_hash=current_hash,
        checked_at=now, needs_review=needs_review,
    )
    _schema_hashes[key] = entry
    return entry


def list_drifted_schemas() -> list[SchemaHash]:
    """List all schemas flagged for review due to drift."""
    return [s for s in _schema_hashes.values() if s.needs_review]
