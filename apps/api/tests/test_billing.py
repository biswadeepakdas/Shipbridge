"""Tests for billing — plans, usage, enforcement, trial, upgrade, API."""

import pytest
from httpx import AsyncClient

from app.services.billing import BillingManager, PlanTier, billing_manager


# --- Unit tests: BillingManager ---

class TestBillingManager:
    def setup_method(self) -> None:
        self.bm = BillingManager()

    def test_initialize_with_trial(self) -> None:
        billing = self.bm.initialize_tenant("t1")
        assert billing.plan == PlanTier.FREE
        assert billing.trial_active is True
        assert billing.limits.max_projects == 10  # Pro limits during trial

    def test_free_limits_after_trial(self) -> None:
        billing = self.bm.initialize_tenant("t1")
        # Set expired trial timestamp (keep trial_active=True so get_billing resolves it)
        billing.trial_ends_at = "2020-01-01T00:00:00+00:00"
        resolved = self.bm.get_billing("t1")
        assert resolved.trial_active is False
        assert resolved.limits.max_projects == 1  # Free limits

    def test_upgrade_to_pro(self) -> None:
        self.bm.initialize_tenant("t1")
        billing = self.bm.upgrade("t1", PlanTier.PRO)
        assert billing.plan == PlanTier.PRO
        assert billing.trial_active is False
        assert billing.limits.max_projects == 10

    def test_upgrade_to_enterprise(self) -> None:
        self.bm.initialize_tenant("t1")
        billing = self.bm.upgrade("t1", PlanTier.ENTERPRISE)
        assert billing.plan == PlanTier.ENTERPRISE
        assert billing.limits.max_projects == 999
        assert billing.limits.priority_support is True

    def test_record_usage(self) -> None:
        self.bm.initialize_tenant("t1")
        self.bm.record_usage("t1", "project")
        self.bm.record_usage("t1", "project")
        billing = self.bm.get_billing("t1")
        assert billing.usage.projects == 2

    def test_check_limit_allowed(self) -> None:
        self.bm.initialize_tenant("t1")
        result = self.bm.check_limit("t1", "project")
        assert result.allowed is True
        assert result.limit == 10  # Pro trial

    def test_check_limit_blocked(self) -> None:
        self.bm.initialize_tenant("t1")
        # Expire trial, switch to free
        billing = self.bm.get_billing("t1")
        billing.trial_active = False
        billing.trial_ends_at = "2020-01-01T00:00:00+00:00"
        billing.plan = PlanTier.FREE
        billing.limits = self.bm._tenants["t1"].limits  # keep as-is for now
        # Force free limits
        from app.services.billing import PLANS
        billing.limits = PLANS[PlanTier.FREE]
        billing.usage.projects = 1

        result = self.bm.check_limit("t1", "project")
        assert result.allowed is False
        assert "Upgrade" in result.message

    def test_check_feature_pro(self) -> None:
        self.bm.initialize_tenant("t1")
        self.bm.upgrade("t1", PlanTier.PRO)
        assert self.bm.check_feature("t1", "staged_deployment") is True
        assert self.bm.check_feature("t1", "compliance_pdf") is True
        assert self.bm.check_feature("t1", "priority_support") is False

    def test_check_feature_free(self) -> None:
        self.bm.initialize_tenant("t1")
        billing = self.bm.get_billing("t1")
        billing.trial_ends_at = "2020-01-01T00:00:00+00:00"  # expire trial
        self.bm.get_billing("t1")  # trigger expiry resolution
        assert self.bm.check_feature("t1", "staged_deployment") is False

    def test_tenant_isolation(self) -> None:
        self.bm.initialize_tenant("t1")
        self.bm.initialize_tenant("t2")
        self.bm.record_usage("t1", "project")
        assert self.bm.get_billing("t1").usage.projects == 1
        assert self.bm.get_billing("t2").usage.projects == 0


# --- API tests ---

@pytest.fixture(autouse=True)
def _reset() -> None:
    billing_manager.clear()


async def _get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Bill User",
        "tenant_name": "Bill Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_list_plans(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()["data"]
    assert len(plans) == 3
    names = [p["name"] for p in plans]
    assert "Free" in names
    assert "Pro" in names
    assert "Enterprise" in names


@pytest.mark.asyncio
async def test_get_current_billing(client: AsyncClient) -> None:
    token = await _get_token(client, "bill1@test.com", "bill-1")
    resp = await client.get("/api/v1/billing/current",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["plan"] == "free"
    assert data["trial_active"] is True


@pytest.mark.asyncio
async def test_upgrade_to_pro(client: AsyncClient) -> None:
    token = await _get_token(client, "bill2@test.com", "bill-2")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/v1/billing/upgrade", headers=headers,
                              json={"plan": "pro"})
    assert resp.status_code == 200
    assert resp.json()["data"]["plan"] == "pro"
    assert resp.json()["data"]["trial_active"] is False


@pytest.mark.asyncio
async def test_check_limit(client: AsyncClient) -> None:
    token = await _get_token(client, "bill3@test.com", "bill-3")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/v1/billing/check-limit", headers=headers,
                              json={"resource_type": "project"})
    assert resp.status_code == 200
    assert resp.json()["data"]["allowed"] is True


@pytest.mark.asyncio
async def test_get_usage(client: AsyncClient) -> None:
    token = await _get_token(client, "bill4@test.com", "bill-4")
    resp = await client.get("/api/v1/billing/usage",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "usage" in data
    assert "limits" in data
    assert "trial_active" in data


@pytest.mark.asyncio
async def test_invalid_plan_upgrade(client: AsyncClient) -> None:
    token = await _get_token(client, "bill5@test.com", "bill-5")
    resp = await client.post("/api/v1/billing/upgrade",
                              headers={"Authorization": f"Bearer {token}"},
                              json={"plan": "invalid"})
    assert resp.status_code == 422
