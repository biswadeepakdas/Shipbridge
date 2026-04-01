"""Tests for subscription engine — filter matching, debounce, CRUD API."""

import time

import pytest
from httpx import AsyncClient

from app.os_layer.subscription_engine import (
    Subscription,
    SubscriptionEngine,
    _evaluate_filter,
)


# --- Unit tests: filter evaluation ---

class TestFilterEvaluation:
    def test_empty_filter_always_matches(self) -> None:
        assert _evaluate_filter("", {"x": 1}) is True
        assert _evaluate_filter(None, {"x": 1}) is True

    def test_equals_numeric(self) -> None:
        assert _evaluate_filter("payload.amount > 10000", {"payload": {"amount": 50000}}) is True
        assert _evaluate_filter("payload.amount > 10000", {"payload": {"amount": 5000}}) is False

    def test_equals_string(self) -> None:
        assert _evaluate_filter("payload.status == closed", {"payload": {"status": "closed"}}) is True
        assert _evaluate_filter("payload.status == closed", {"payload": {"status": "open"}}) is False

    def test_contains(self) -> None:
        assert _evaluate_filter("payload.text contains urgent", {"payload": {"text": "This is urgent!"}}) is True
        assert _evaluate_filter("payload.text contains urgent", {"payload": {"text": "Normal message"}}) is False

    def test_exists(self) -> None:
        assert _evaluate_filter("payload.email exists", {"payload": {"email": "a@b.com"}}) is True
        assert _evaluate_filter("payload.email exists", {"payload": {}}) is False

    def test_greater_than(self) -> None:
        assert _evaluate_filter("payload.score >= 75", {"payload": {"score": 80}}) is True
        assert _evaluate_filter("payload.score >= 75", {"payload": {"score": 70}}) is False

    def test_less_than(self) -> None:
        assert _evaluate_filter("payload.priority < 3", {"payload": {"priority": 1}}) is True
        assert _evaluate_filter("payload.priority < 3", {"payload": {"priority": 5}}) is False

    def test_not_equals(self) -> None:
        assert _evaluate_filter("payload.status != draft", {"payload": {"status": "active"}}) is True
        assert _evaluate_filter("payload.status != draft", {"payload": {"status": "draft"}}) is False

    def test_missing_field_returns_false(self) -> None:
        assert _evaluate_filter("payload.missing > 10", {"payload": {}}) is False


# --- Unit tests: subscription matching ---

class TestSubscriptionEngine:
    def _make_engine(self) -> SubscriptionEngine:
        engine = SubscriptionEngine()
        engine.register(Subscription(
            id="s1", tenant_id="t1", name="High value deals",
            event_type="deal.closed", filter_expression="payload.amount > 10000",
            agent_id="sales-agent", debounce_seconds=0,
        ))
        engine.register(Subscription(
            id="s2", tenant_id="t1", name="All messages",
            event_type="message.new", agent_id="support-agent",
        ))
        engine.register(Subscription(
            id="s3", tenant_id="t2", name="Other tenant",
            event_type="deal.closed", agent_id="other-agent",
        ))
        return engine

    def test_matches_by_event_type(self) -> None:
        engine = self._make_engine()
        result = engine.match_event("message.new", {}, tenant_id="t1")
        assert result.total_matched == 1
        assert result.matches[0].agent_id == "support-agent"

    def test_filter_blocks_non_matching(self) -> None:
        engine = self._make_engine()
        result = engine.match_event("deal.closed", {"payload": {"amount": 5000}}, tenant_id="t1")
        assert result.total_matched == 0

    def test_filter_passes_matching(self) -> None:
        engine = self._make_engine()
        result = engine.match_event("deal.closed", {"payload": {"amount": 50000}}, tenant_id="t1")
        assert result.total_matched == 1
        assert result.matches[0].agent_id == "sales-agent"

    def test_tenant_isolation(self) -> None:
        engine = self._make_engine()
        result = engine.match_event("deal.closed", {"payload": {"amount": 50000}}, tenant_id="t2")
        assert result.total_matched == 1
        assert result.matches[0].agent_id == "other-agent"

    def test_no_match_returns_empty(self) -> None:
        engine = self._make_engine()
        result = engine.match_event("unknown.event", {}, tenant_id="t1")
        assert result.total_matched == 0

    def test_debounce_blocks_rapid_triggers(self) -> None:
        engine = SubscriptionEngine()
        engine.register(Subscription(
            id="s1", tenant_id="t1", name="Debounced",
            event_type="alert", agent_id="agent1", debounce_seconds=60,
        ))
        r1 = engine.match_event("alert", {}, tenant_id="t1")
        assert r1.total_matched == 1
        assert r1.total_debounced == 0

        r2 = engine.match_event("alert", {}, tenant_id="t1")
        assert r2.total_matched == 0
        assert r2.total_debounced == 1

    def test_wildcard_event_type(self) -> None:
        engine = SubscriptionEngine()
        engine.register(Subscription(
            id="s1", tenant_id="t1", name="Catch all",
            event_type="*", agent_id="logger",
        ))
        result = engine.match_event("anything.here", {}, tenant_id="t1")
        assert result.total_matched == 1

    def test_remove_subscription(self) -> None:
        engine = self._make_engine()
        assert engine.remove("s1") is True
        result = engine.match_event("deal.closed", {"payload": {"amount": 50000}}, tenant_id="t1")
        assert result.total_matched == 0

    def test_list_by_tenant(self) -> None:
        engine = self._make_engine()
        subs = engine.list_subscriptions("t1")
        assert len(subs) == 2


# --- API endpoint tests ---

@pytest.fixture(autouse=True)
def _reset() -> None:
    from app.os_layer.subscription_engine import subscription_engine
    subscription_engine.clear()


async def _get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Sub User",
        "tenant_name": "Sub Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_create_subscription(client: AsyncClient) -> None:
    token = await _get_token(client, "sub1@test.com", "sub-1")
    resp = await client.post("/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Deal alerts", "event_type": "deal.closed",
              "filter_expression": "payload.amount > 10000", "agent_id": "sales-bot"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Deal alerts"
    assert data["event_type"] == "deal.closed"
    assert data["agent_id"] == "sales-bot"


@pytest.mark.asyncio
async def test_list_subscriptions(client: AsyncClient) -> None:
    token = await _get_token(client, "sub2@test.com", "sub-2")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/subscriptions", headers=headers,
        json={"name": "S1", "event_type": "e1", "agent_id": "a1"})
    await client.post("/api/v1/subscriptions", headers=headers,
        json={"name": "S2", "event_type": "e2", "agent_id": "a2"})
    resp = await client.get("/api/v1/subscriptions", headers=headers)
    assert len(resp.json()["data"]) == 2


@pytest.mark.asyncio
async def test_delete_subscription(client: AsyncClient) -> None:
    token = await _get_token(client, "sub3@test.com", "sub-3")
    headers = {"Authorization": f"Bearer {token}"}
    create = await client.post("/api/v1/subscriptions", headers=headers,
        json={"name": "Temp", "event_type": "t", "agent_id": "a"})
    sub_id = create.json()["data"]["id"]
    del_resp = await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=headers)
    assert del_resp.status_code == 200
    list_resp = await client.get("/api/v1/subscriptions", headers=headers)
    assert len(list_resp.json()["data"]) == 0


@pytest.mark.asyncio
async def test_test_match_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client, "sub4@test.com", "sub-4")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/subscriptions", headers=headers,
        json={"name": "Big deals", "event_type": "deal.closed",
              "filter_expression": "payload.amount > 10000", "agent_id": "sales"})

    resp = await client.post("/api/v1/subscriptions/test-match", headers=headers,
        json={"event_type": "deal.closed", "payload": {"payload": {"amount": 50000}}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_matched"] == 1
