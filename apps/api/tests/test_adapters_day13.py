"""Tests for Slack, HubSpot, and Stripe adapters — fetch, health_check, normalize."""

import pytest

from app.integrations.adapters.hubspot import HubSpotAdapter
from app.integrations.adapters.slack import SlackAdapter
from app.integrations.adapters.stripe import StripeAdapter
from app.integrations.adapters import ADAPTER_REGISTRY


# --- Slack Adapter ---

class TestSlackAdapter:
    @pytest.fixture
    def adapter(self) -> SlackAdapter:
        return SlackAdapter(bot_token="xoxb-test")

    @pytest.mark.asyncio
    async def test_fetch_messages(self, adapter: SlackAdapter) -> None:
        result = await adapter.fetch({"type": "messages", "channel": "C01GENERAL"})
        assert result["ok"] is True
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_channels(self, adapter: SlackAdapter) -> None:
        result = await adapter.fetch({"type": "channels"})
        assert len(result["channels"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_thread(self, adapter: SlackAdapter) -> None:
        result = await adapter.fetch({"type": "thread"})
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: SlackAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"

    def test_normalize_messages(self, adapter: SlackAdapter) -> None:
        raw = {
            "ok": True, "type": "messages", "channel": "C01GENERAL",
            "messages": [
                {"user_name": "alice", "text": "Deployed v2.3", "ts": "1711900000"},
                {"user_name": "bob", "text": "LGTM", "ts": "1711900060"},
            ],
        }
        normalized = adapter.normalize(raw)
        assert normalized.source == "slack"
        assert normalized.data_type == "messages"
        assert "**@alice**" in normalized.content
        assert "Deployed v2.3" in normalized.content
        assert "**@bob**" in normalized.content
        assert normalized.metadata["message_count"] == 2

    def test_normalize_channels(self, adapter: SlackAdapter) -> None:
        raw = {
            "ok": True, "type": "channels",
            "channels": [
                {"name": "general", "num_members": 45, "topic": {"value": "Announcements"}},
                {"name": "engineering", "num_members": 18, "topic": {"value": "Eng talks"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "#general" in normalized.content
        assert "#engineering" in normalized.content
        assert "45" in normalized.content

    def test_normalize_thread(self, adapter: SlackAdapter) -> None:
        raw = {
            "ok": True, "type": "thread",
            "messages": [
                {"user_name": "alice", "text": "Latency spikes?", "ts": "1"},
                {"user_name": "bob", "text": "Investigating", "ts": "2"},
            ],
        }
        normalized = adapter.normalize(raw)
        assert normalized.data_type == "thread"
        assert "Thread" in normalized.content


# --- HubSpot Adapter ---

class TestHubSpotAdapter:
    @pytest.fixture
    def adapter(self) -> HubSpotAdapter:
        return HubSpotAdapter(access_token="pat-test")

    @pytest.mark.asyncio
    async def test_fetch_contacts(self, adapter: HubSpotAdapter) -> None:
        result = await adapter.fetch({"object": "contacts"})
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_companies(self, adapter: HubSpotAdapter) -> None:
        result = await adapter.fetch({"object": "companies"})
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_deals(self, adapter: HubSpotAdapter) -> None:
        result = await adapter.fetch({"object": "deals"})
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_activities(self, adapter: HubSpotAdapter) -> None:
        result = await adapter.fetch({"object": "activities"})
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: HubSpotAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"

    def test_normalize_contacts(self, adapter: HubSpotAdapter) -> None:
        raw = {
            "objectType": "contacts",
            "results": [
                {"id": "1", "properties": {"firstname": "Jane", "lastname": "Doe",
                 "email": "jane@acme.com", "company": "Acme", "lifecyclestage": "customer"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Jane Doe" in normalized.content
        assert "jane@acme.com" in normalized.content
        assert "customer" in normalized.content

    def test_normalize_companies(self, adapter: HubSpotAdapter) -> None:
        raw = {
            "objectType": "companies",
            "results": [
                {"id": "1", "properties": {"name": "Acme Corp", "industry": "Technology",
                 "annualrevenue": "5000000", "numberofemployees": "250", "city": "SF"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Acme Corp" in normalized.content
        assert "$5,000,000" in normalized.content

    def test_normalize_deals(self, adapter: HubSpotAdapter) -> None:
        raw = {
            "objectType": "deals",
            "results": [
                {"id": "1", "properties": {"dealname": "Enterprise License", "amount": "95000",
                 "dealstage": "closedwon", "closedate": "2026-03-15"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Enterprise License" in normalized.content
        assert "$95,000" in normalized.content

    def test_normalize_activities(self, adapter: HubSpotAdapter) -> None:
        raw = {
            "objectType": "activities",
            "results": [
                {"id": "1", "properties": {"hs_activity_type": "CALL", "hs_call_title": "Discovery call",
                 "hs_timestamp": "2026-03-28T14:00:00Z", "hs_call_duration": "1800000"}},
                {"id": "2", "properties": {"hs_activity_type": "EMAIL", "hs_email_subject": "Follow-up",
                 "hs_timestamp": "2026-03-29T09:00:00Z"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Discovery call" in normalized.content
        assert "30 min" in normalized.content
        assert "Follow-up" in normalized.content


# --- Stripe Adapter ---

class TestStripeAdapter:
    @pytest.fixture
    def adapter(self) -> StripeAdapter:
        return StripeAdapter(api_key="sk_test_xxx")

    @pytest.mark.asyncio
    async def test_fetch_payments(self, adapter: StripeAdapter) -> None:
        result = await adapter.fetch({"object": "payments"})
        assert len(result["data"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_customers(self, adapter: StripeAdapter) -> None:
        result = await adapter.fetch({"object": "customers"})
        assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_subscriptions(self, adapter: StripeAdapter) -> None:
        result = await adapter.fetch({"object": "subscriptions"})
        assert len(result["data"]) == 3

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: StripeAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"

    def test_normalize_payments(self, adapter: StripeAdapter) -> None:
        raw = {
            "objectType": "payments",
            "data": [
                {"id": "pi_001", "amount": 9900, "currency": "usd", "status": "succeeded",
                 "description": "Pro Plan"},
                {"id": "pi_002", "amount": 2900, "currency": "usd", "status": "failed",
                 "description": "Upgrade", "failure_message": "Card declined"},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "$99.00" in normalized.content
        assert "succeeded" in normalized.content
        assert "Card declined" in normalized.content

    def test_normalize_customers(self, adapter: StripeAdapter) -> None:
        raw = {
            "objectType": "customers",
            "data": [
                {"id": "cus_001", "name": "Acme Corp", "email": "billing@acme.com",
                 "subscriptions": {"data": [{"status": "active", "plan": {"nickname": "Pro"}}]}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Acme Corp" in normalized.content
        assert "Pro" in normalized.content
        assert "active" in normalized.content

    def test_normalize_subscriptions(self, adapter: StripeAdapter) -> None:
        raw = {
            "objectType": "subscriptions",
            "data": [
                {"id": "sub_001", "status": "active",
                 "plan": {"nickname": "Enterprise", "amount": 19900, "interval": "month"}},
                {"id": "sub_002", "status": "canceled", "canceled_at": 1711800000,
                 "plan": {"nickname": "Pro", "amount": 2900, "interval": "month"}},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "$199.00/month" in normalized.content
        assert "Enterprise" in normalized.content
        assert "canceled" in normalized.content

    def test_normalize_empty(self, adapter: StripeAdapter) -> None:
        raw = {"objectType": "payments", "data": []}
        normalized = adapter.normalize(raw)
        assert "0 records" in normalized.content


# --- Adapter Registry ---

class TestAdapterRegistry:
    def test_all_five_adapters_registered(self) -> None:
        assert len(ADAPTER_REGISTRY) >= 5
        assert "salesforce" in ADAPTER_REGISTRY
        assert "notion" in ADAPTER_REGISTRY
        assert "slack" in ADAPTER_REGISTRY
        assert "hubspot" in ADAPTER_REGISTRY
        assert "stripe" in ADAPTER_REGISTRY
