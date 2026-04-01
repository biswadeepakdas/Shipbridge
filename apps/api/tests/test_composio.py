"""Tests for Composio integration — proxy adapter, rule registry, JMESPath, unknown queue, normalizer."""

import pytest

from app.integrations.adapters.composio_proxy import ComposioProxyAdapter
from app.os_layer.jmespath_executor import NormalizedEvent, execute_rule
from app.os_layer.normalizer import normalize_event
from app.os_layer.rule_registry import NormalizationRuleEntry, RuleRegistry
from app.os_layer.unknown_event_queue import UnknownEvent, UnknownEventQueue


# --- ComposioProxyAdapter ---

class TestComposioProxyAdapter:
    @pytest.fixture
    def adapter(self) -> ComposioProxyAdapter:
        return ComposioProxyAdapter(api_key="test", app_name="jira")

    @pytest.mark.asyncio
    async def test_fetch_returns_composio_envelope(self, adapter: ComposioProxyAdapter) -> None:
        result = await adapter.fetch({"action": "list_issues", "app": "jira"})
        assert result["source"] == "composio"
        assert result["app"] == "jira"
        assert len(result["data"]["items"]) == 2

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: ComposioProxyAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"

    def test_normalize_composio_response(self, adapter: ComposioProxyAdapter) -> None:
        raw = {
            "source": "composio", "app": "jira", "action": "list_issues",
            "trigger": "jira.list_issues",
            "data": {"items": [
                {"id": "c1", "title": "Jira issue 1", "status": "open"},
            ], "total": 1},
        }
        n = adapter.normalize(raw)
        assert n.source == "composio:jira"
        assert "Jira issue 1" in n.content
        assert n.metadata["app"] == "jira"

    def test_normalize_empty(self, adapter: ComposioProxyAdapter) -> None:
        raw = {"source": "composio", "app": "unknown", "action": "test",
               "data": {"items": [], "total": 0}}
        n = adapter.normalize(raw)
        assert "0 items" in n.content


# --- RuleRegistry ---

class TestRuleRegistry:
    def test_register_and_lookup(self) -> None:
        reg = RuleRegistry()
        rule = NormalizationRuleEntry(
            rule_id="r1", app="salesforce", trigger="opportunity_closed",
            payload_map={"event_type": "deal.closed", "amount": "payload.Amount"},
            status="active", version=1,
        )
        reg.register(rule)
        found = reg.lookup("salesforce", "opportunity_closed")
        assert found is not None
        assert found.rule_id == "r1"

    def test_lookup_returns_none_for_draft(self) -> None:
        reg = RuleRegistry()
        rule = NormalizationRuleEntry(
            rule_id="r2", app="slack", trigger="message",
            payload_map={}, status="draft", version=1,
        )
        reg.register(rule)
        assert reg.lookup("slack", "message") is None

    def test_promote_draft_to_active(self) -> None:
        reg = RuleRegistry()
        rule = NormalizationRuleEntry(
            rule_id="r3", app="notion", trigger="page_updated",
            payload_map={"event_type": "page.update"}, status="draft", version=1,
        )
        reg.register(rule)
        assert reg.promote("notion", "page_updated") is True
        assert reg.lookup("notion", "page_updated") is not None

    def test_archive_rule(self) -> None:
        reg = RuleRegistry()
        rule = NormalizationRuleEntry(
            rule_id="r4", app="github", trigger="push",
            payload_map={"event_type": "code.push"}, status="active", version=1,
        )
        reg.register(rule)
        assert reg.archive("github", "push") is True
        assert reg.lookup("github", "push") is None

    def test_list_rules_by_app(self) -> None:
        reg = RuleRegistry()
        reg.register(NormalizationRuleEntry(rule_id="r1", app="sf", trigger="t1", payload_map={}, status="active", version=1))
        reg.register(NormalizationRuleEntry(rule_id="r2", app="sf", trigger="t2", payload_map={}, status="active", version=1))
        reg.register(NormalizationRuleEntry(rule_id="r3", app="slack", trigger="t3", payload_map={}, status="active", version=1))
        assert len(reg.list_rules("sf")) == 2
        assert len(reg.list_rules("slack")) == 1


# --- JMESPath Executor ---

class TestJMESPathExecutor:
    def test_resolve_simple_path(self) -> None:
        import jmespath
        data = {"payload": {"Amount": 50000}}
        assert jmespath.search("payload.Amount", data) == 50000

    def test_resolve_nested_path(self) -> None:
        import jmespath
        data = {"data": {"items": [{"name": "first"}]}}
        assert jmespath.search("data.items[0].name", data) == "first"

    def test_resolve_missing_returns_none(self) -> None:
        import jmespath
        assert jmespath.search("b.c", {"a": 1}) is None

    def test_resolve_array_out_of_bounds(self) -> None:
        import jmespath
        data = {"items": [{"x": 1}]}
        assert jmespath.search("items[5].x", data) is None

    def test_execute_rule_produces_event(self) -> None:
        rule = NormalizationRuleEntry(
            rule_id="r1", app="salesforce", trigger="opp_closed",
            payload_map={
                "event_type": "deal.closed",
                "amount": "payload.Amount",
                "deal_name": "payload.Name",
            },
            status="active", version=2,
        )
        raw = {"payload": {"Amount": 125000, "Name": "Acme Enterprise"}}
        event = execute_rule(rule, raw)
        assert event is not None
        assert event.event_type == "deal.closed"
        assert event.payload["amount"] == 125000
        assert event.payload["deal_name"] == "Acme Enterprise"
        assert event.rule_version == 2

    def test_execute_rule_with_literal_values(self) -> None:
        rule = NormalizationRuleEntry(
            rule_id="r2", app="custom", trigger="test",
            payload_map={"event_type": "custom.event", "source_label": "my_app"},
            status="active", version=1,
        )
        event = execute_rule(rule, {})
        assert event is not None
        assert event.event_type == "custom.event"
        assert event.payload["source_label"] == "my_app"

    def test_execute_rule_no_event_type_returns_none(self) -> None:
        rule = NormalizationRuleEntry(
            rule_id="r3", app="bad", trigger="test",
            payload_map={"amount": "payload.x"},  # no event_type
            status="active", version=1,
        )
        assert execute_rule(rule, {"payload": {"x": 1}}) is None


# --- UnknownEventQueue ---

class TestUnknownEventQueue:
    def test_enqueue_and_drain(self) -> None:
        q = UnknownEventQueue()
        q.enqueue(UnknownEvent(id="e1", app="trello", trigger="card_moved", raw_payload={}, received_at="now"))
        q.enqueue(UnknownEvent(id="e2", app="trello", trigger="card_created", raw_payload={}, received_at="now"))
        assert q.size == 2
        batch = q.drain(limit=1)
        assert len(batch) == 1
        assert batch[0].id == "e1"
        assert q.size == 1

    def test_drain_empties_queue(self) -> None:
        q = UnknownEventQueue()
        q.enqueue(UnknownEvent(id="e1", app="x", trigger="y", raw_payload={}, received_at="now"))
        q.drain()
        assert q.size == 0

    def test_peek_does_not_remove(self) -> None:
        q = UnknownEventQueue()
        q.enqueue(UnknownEvent(id="e1", app="x", trigger="y", raw_payload={}, received_at="now"))
        peeked = q.peek()
        assert len(peeked) == 1
        assert q.size == 1


# --- Normalizer Pipeline ---

class TestNormalizerPipeline:
    def setup_method(self) -> None:
        """Reset singletons before each test."""
        from app.os_layer.rule_registry import rule_registry
        from app.os_layer.unknown_event_queue import unknown_event_queue
        rule_registry.clear()
        unknown_event_queue.clear()

    def test_known_trigger_normalizes(self) -> None:
        from app.os_layer.rule_registry import rule_registry
        rule_registry.register(NormalizationRuleEntry(
            rule_id="r1", app="salesforce", trigger="opportunity_closed",
            payload_map={"event_type": "deal.closed", "amount": "payload.Amount"},
            status="active", version=1,
        ))
        result = normalize_event("salesforce", "opportunity_closed", {"payload": {"Amount": 50000}})
        assert result.success is True
        assert result.normalized is not None
        assert result.normalized.event_type == "deal.closed"

    def test_unknown_trigger_queued(self) -> None:
        from app.os_layer.unknown_event_queue import unknown_event_queue
        result = normalize_event("trello", "card_moved", {"card": {"name": "test"}}, tenant_id="t1")
        assert result.success is False
        assert result.queued_as_unknown is True
        assert unknown_event_queue.size == 1

    def test_unknown_event_has_correct_fields(self) -> None:
        from app.os_layer.unknown_event_queue import unknown_event_queue
        normalize_event("asana", "task_completed", {"task_id": "123"}, tenant_id="t2")
        events = unknown_event_queue.peek()
        assert events[0].app == "asana"
        assert events[0].trigger == "task_completed"
        assert events[0].tenant_id == "t2"
