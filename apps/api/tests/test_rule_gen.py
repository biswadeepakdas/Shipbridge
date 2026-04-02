"""Tests for LLM rule generator, promotion flow, schema drift, and API endpoints."""

import pytest
from httpx import AsyncClient

from app.os_layer.rule_registry import NormalizationRuleEntry, rule_registry
from app.os_layer.unknown_event_queue import UnknownEvent, unknown_event_queue
from app.workers.rule_gen import (
    RuleGenerationResult,
    check_schema_drift,
    compute_schema_hash,
    list_drifted_schemas,
    run_rule_generator,
    _generate_payload_map_from_sample,
    _schema_hashes,
)


# --- Unit tests: payload map generation ---

class TestPayloadMapGeneration:
    def test_generates_event_type(self) -> None:
        pm = _generate_payload_map_from_sample("salesforce", "opportunity_closed", {})
        assert pm["event_type"] == "salesforce.opportunity.closed"

    def test_maps_common_fields(self) -> None:
        sample = {"id": "123", "name": "Deal", "status": "won", "amount": 50000}
        pm = _generate_payload_map_from_sample("sf", "opp", sample)
        assert "id" in pm
        assert pm["id"] == "payload.id"
        assert "amount" in pm

    def test_handles_nested_payload(self) -> None:
        sample = {"data": {"id": "456", "title": "Nested item"}}
        pm = _generate_payload_map_from_sample("app", "trigger", sample)
        # Should find id and title in nested data
        assert any("data" in v for v in pm.values() if isinstance(v, str) and "payload" in v)

    def test_handles_empty_payload(self) -> None:
        pm = _generate_payload_map_from_sample("app", "trigger", {})
        assert "event_type" in pm


# --- Unit tests: rule generator job ---

class TestRuleGeneratorJob:
    def setup_method(self) -> None:
        rule_registry.clear()
        unknown_event_queue.clear()

    def test_generates_draft_rule_from_unknown(self) -> None:
        unknown_event_queue.enqueue(UnknownEvent(
            id="e1", app="trello", trigger="card_moved",
            raw_payload={"id": "card-1", "name": "Task", "status": "done"},
            received_at="now",
        ))
        result = run_rule_generator()
        assert result.processed == 1
        assert result.generated == 1
        assert result.rules[0].rule.status == "draft"
        assert result.rules[0].rule.app == "trello"

    def test_deduplicates_same_trigger(self) -> None:
        for i in range(3):
            unknown_event_queue.enqueue(UnknownEvent(
                id=f"e{i}", app="asana", trigger="task_complete",
                raw_payload={"id": str(i)}, received_at="now",
            ))
        result = run_rule_generator()
        assert result.generated == 1  # Only one rule for same trigger

    def test_skips_existing_rules(self) -> None:
        rule_registry.register(NormalizationRuleEntry(
            rule_id="existing", app="slack", trigger="message",
            payload_map={"event_type": "slack.message"}, status="active", version=1,
        ))
        unknown_event_queue.enqueue(UnknownEvent(
            id="e1", app="slack", trigger="message",
            raw_payload={}, received_at="now",
        ))
        result = run_rule_generator()
        assert result.generated == 0

    def test_empty_queue_returns_zero(self) -> None:
        result = run_rule_generator()
        assert result.processed == 0
        assert result.generated == 0

    def test_draft_rule_registered_in_registry(self) -> None:
        unknown_event_queue.enqueue(UnknownEvent(
            id="e1", app="monday", trigger="item_created",
            raw_payload={"id": "1", "name": "New item"}, received_at="now",
        ))
        run_rule_generator()
        rules = rule_registry.list_rules("monday")
        assert len(rules) == 1
        assert rules[0].status == "draft"


# --- Unit tests: schema drift detection ---

class TestSchemaDrift:
    def setup_method(self) -> None:
        _schema_hashes.clear()

    def test_first_check_no_drift(self) -> None:
        result = check_schema_drift("app", "trigger", {"field": "string"})
        assert result.needs_review is False

    def test_same_schema_no_drift(self) -> None:
        schema = {"field": "string", "count": "integer"}
        check_schema_drift("app", "trigger", schema)
        result = check_schema_drift("app", "trigger", schema)
        assert result.needs_review is False

    def test_changed_schema_flags_drift(self) -> None:
        check_schema_drift("app", "trigger", {"field": "string"})
        result = check_schema_drift("app", "trigger", {"field": "string", "new_field": "boolean"})
        assert result.needs_review is True

    def test_list_drifted_schemas(self) -> None:
        check_schema_drift("a", "t1", {"v": 1})
        check_schema_drift("a", "t1", {"v": 2})  # drift
        check_schema_drift("b", "t2", {"v": 1})  # no drift
        drifted = list_drifted_schemas()
        assert len(drifted) == 1
        assert drifted[0].app == "a"

    def test_hash_deterministic(self) -> None:
        h1 = compute_schema_hash("a", "t", {"b": 1, "a": 2})
        h2 = compute_schema_hash("a", "t", {"a": 2, "b": 1})
        assert h1 == h2  # sort_keys ensures determinism


# --- API endpoint tests ---

async def _signup_and_get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Rule User",
        "tenant_name": "Rule Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    """Reset rule registry and unknown queue before each test."""
    rule_registry.clear()
    unknown_event_queue.clear()
    _schema_hashes.clear()


@pytest.mark.asyncio
async def test_list_rules_endpoint(client: AsyncClient) -> None:
    token = await _signup_and_get_token(client, "rule1@test.com", "rule-1")
    resp = await client.get("/api/v1/rules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "rules" in data
    assert "unknown_queue_size" in data


@pytest.mark.asyncio
async def test_generate_and_promote_flow(client: AsyncClient) -> None:
    """Full flow: queue unknown → generate draft → promote to active."""
    token = await _signup_and_get_token(client, "rule2@test.com", "rule-2")
    headers = {"Authorization": f"Bearer {token}"}

    # Queue an unknown event
    unknown_event_queue.enqueue(UnknownEvent(
        id="e1", app="jira", trigger="issue_created",
        raw_payload={"id": "JIRA-1", "title": "Bug fix", "status": "open"},
        received_at="now",
    ))

    # Generate rules
    gen_resp = await client.post("/api/v1/rules/generate", headers=headers)
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()["data"]
    assert gen_data["generated"] == 1

    # Verify draft exists
    list_resp = await client.get("/api/v1/rules?app=jira", headers=headers)
    rules = list_resp.json()["data"]["rules"]
    assert len(rules) >= 1
    assert rules[0]["status"] == "draft"

    # Promote
    promote_resp = await client.post("/api/v1/rules/promote", headers=headers,
                                      json={"app": "jira", "trigger": "issue_created"})
    assert promote_resp.status_code == 200

    # Verify active
    list_resp2 = await client.get("/api/v1/rules?app=jira", headers=headers)
    rules2 = list_resp2.json()["data"]["rules"]
    assert rules2[0]["status"] == "active"


@pytest.mark.asyncio
async def test_schema_check_endpoint(client: AsyncClient) -> None:
    token = await _signup_and_get_token(client, "rule3@test.com", "rule-3")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/rules/schema-check", headers=headers,
                              json={"app": "sf", "trigger": "opp", "trigger_schema": {"amount": "number"}})
    assert resp.status_code == 200
    assert resp.json()["data"]["needs_review"] is False


@pytest.mark.asyncio
async def test_schema_drift_endpoint(client: AsyncClient) -> None:
    token = await _signup_and_get_token(client, "rule4@test.com", "rule-4")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/rules/schema-drift", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
