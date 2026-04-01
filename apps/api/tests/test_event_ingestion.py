"""Tests for event ingestion — webhook receiver, dedup, DLQ, normalization pipeline."""

import pytest
from httpx import AsyncClient

from app.os_layer.dead_letter_queue import DeadLetterQueue
from app.os_layer.dedup import DeduplicationEngine
from app.os_layer.event_ingestion import generate_dedup_key, ingest_webhook_event
from app.os_layer.rule_registry import NormalizationRuleEntry, rule_registry
from app.os_layer.unknown_event_queue import unknown_event_queue


# --- Unit tests: DeduplicationEngine ---

class TestDeduplicationEngine:
    def test_first_event_not_duplicate(self) -> None:
        engine = DeduplicationEngine()
        assert engine.is_duplicate("key-1") is False

    def test_second_event_is_duplicate(self) -> None:
        engine = DeduplicationEngine()
        engine.is_duplicate("key-1")
        assert engine.is_duplicate("key-1") is True

    def test_different_keys_not_duplicate(self) -> None:
        engine = DeduplicationEngine()
        engine.is_duplicate("key-1")
        assert engine.is_duplicate("key-2") is False

    def test_expired_key_not_duplicate(self) -> None:
        engine = DeduplicationEngine(ttl_seconds=0)
        engine.is_duplicate("key-1")
        # TTL=0 means immediate expiry
        assert engine.is_duplicate("key-1") is False

    def test_stats_tracking(self) -> None:
        engine = DeduplicationEngine()
        engine.is_duplicate("a")
        engine.is_duplicate("a")  # duplicate
        engine.is_duplicate("b")
        stats = engine.stats
        assert stats["total_checked"] == 3
        assert stats["total_duplicates"] == 1
        assert stats["active_keys"] == 2


# --- Unit tests: Dead Letter Queue ---

class TestDeadLetterQueue:
    def test_add_and_list(self) -> None:
        dlq = DeadLetterQueue()
        dlq.add("e1", "slack", "message", {"text": "hi"}, "timeout", 3, "2026-03-30")
        entries = dlq.list_entries()
        assert len(entries) == 1
        assert entries[0].failure_reason == "timeout"
        assert entries[0].retry_count == 3

    def test_list_newest_first(self) -> None:
        dlq = DeadLetterQueue()
        dlq.add("e1", "a", "t1", {}, "err1", 1, "2026-03-30")
        dlq.add("e2", "b", "t2", {}, "err2", 2, "2026-03-31")
        entries = dlq.list_entries()
        assert entries[0].id == "e2"  # newest first

    def test_size(self) -> None:
        dlq = DeadLetterQueue()
        assert dlq.size == 0
        dlq.add("e1", "x", "y", {}, "err", 0, "now")
        assert dlq.size == 1


# --- Unit tests: dedup key generation ---

class TestDedupKeyGeneration:
    def test_uses_id_field(self) -> None:
        key = generate_dedup_key("slack", {"id": "msg-123"})
        assert key == "slack:msg-123"

    def test_uses_event_id_field(self) -> None:
        key = generate_dedup_key("hubspot", {"event_id": "evt-456"})
        assert key == "hubspot:evt-456"

    def test_hashes_payload_without_id(self) -> None:
        key = generate_dedup_key("custom", {"data": "value"})
        assert key.startswith("custom:")
        assert len(key) > len("custom:")

    def test_deterministic(self) -> None:
        k1 = generate_dedup_key("p", {"a": 1, "b": 2})
        k2 = generate_dedup_key("p", {"a": 1, "b": 2})
        assert k1 == k2


# --- Unit tests: full ingestion pipeline ---

class TestEventIngestion:
    def setup_method(self) -> None:
        rule_registry.clear()
        unknown_event_queue.clear()
        from app.os_layer.dedup import dedup_engine
        dedup_engine.clear()

    def test_processes_event_with_matching_rule(self) -> None:
        rule_registry.register(NormalizationRuleEntry(
            rule_id="r1", app="salesforce", trigger="opportunity_closed",
            payload_map={"event_type": "deal.closed", "amount": "payload.Amount"},
            status="active", version=1,
        ))
        result = ingest_webhook_event(
            provider="salesforce",
            payload={"app": "salesforce", "trigger": "opportunity_closed", "payload": {"Amount": 50000}},
        )
        assert result.status == "processed"
        assert result.normalized_event_type == "deal.closed"

    def test_queues_unknown_trigger(self) -> None:
        result = ingest_webhook_event(
            provider="trello",
            payload={"app": "trello", "trigger": "card_moved", "id": "trello-1"},
        )
        assert result.status == "queued_unknown"
        assert unknown_event_queue.size == 1

    def test_deduplicates_same_event(self) -> None:
        result1 = ingest_webhook_event(provider="slack", payload={"id": "msg-123", "trigger": "test"})
        result2 = ingest_webhook_event(provider="slack", payload={"id": "msg-123", "trigger": "test"})
        assert result1.status in ("processed", "queued_unknown")
        assert result2.status == "duplicate"

    def test_different_events_not_deduped(self) -> None:
        result1 = ingest_webhook_event(provider="p", payload={"id": "e1", "trigger": "t"})
        result2 = ingest_webhook_event(provider="p", payload={"id": "e2", "trigger": "t"})
        assert result1.status != "duplicate"
        assert result2.status != "duplicate"


# --- API endpoint tests ---

@pytest.fixture(autouse=True)
def _reset() -> None:
    rule_registry.clear()
    unknown_event_queue.clear()
    from app.os_layer.dedup import dedup_engine
    from app.os_layer.dead_letter_queue import dead_letter_queue
    dedup_engine.clear()
    dead_letter_queue.clear()


@pytest.mark.asyncio
async def test_webhook_receiver_endpoint(client: AsyncClient) -> None:
    """Webhook receiver processes event and returns result."""
    resp = await client.post("/webhooks/salesforce", json={
        "id": "sf-evt-001",
        "app": "salesforce",
        "trigger": "lead_created",
        "payload": {"name": "Test Lead"},
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["provider"] == "salesforce"
    assert data["status"] in ("processed", "queued_unknown")


@pytest.mark.asyncio
async def test_webhook_dedup_on_second_call(client: AsyncClient) -> None:
    """Second identical webhook is deduplicated."""
    payload = {"id": "dedup-test-001", "trigger": "test", "app": "test"}
    await client.post("/webhooks/test", json=payload)
    resp2 = await client.post("/webhooks/test", json=payload)
    assert resp2.json()["data"]["status"] == "duplicate"


@pytest.mark.asyncio
async def test_webhook_with_matching_rule(client: AsyncClient) -> None:
    """Webhook with matching rule returns processed status."""
    rule_registry.register(NormalizationRuleEntry(
        rule_id="api-r1", app="stripe", trigger="payment_succeeded",
        payload_map={"event_type": "payment.success", "amount": "payload.amount"},
        status="active", version=1,
    ))
    resp = await client.post("/webhooks/stripe", json={
        "id": "stripe-001", "app": "stripe", "trigger": "payment_succeeded",
        "payload": {"amount": 9900},
    })
    assert resp.json()["data"]["status"] == "processed"
    assert resp.json()["data"]["normalized_event_type"] == "payment.success"


@pytest.mark.asyncio
async def test_pipeline_stats_endpoint(client: AsyncClient) -> None:
    """Pipeline stats returns dedup and DLQ info."""
    resp = await client.get("/api/v1/events/pipeline-stats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "dedup" in data
    assert "dlq_size" in data


@pytest.mark.asyncio
async def test_dlq_endpoint(client: AsyncClient) -> None:
    """DLQ endpoint returns list of dead-lettered events."""
    resp = await client.get("/api/v1/events/dlq")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
