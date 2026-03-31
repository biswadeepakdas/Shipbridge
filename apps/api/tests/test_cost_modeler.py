"""Tests for cost modeler — pricing, routing, cache estimation, projections, API."""

import pytest
from httpx import AsyncClient

from app.services.cost_modeler import (
    MODEL_PRICING,
    TaskDistribution,
    TokenEstimate,
    classify_model_tier,
    estimate_cache_hit_rate,
    get_optimal_routing,
    project_costs,
)


# --- Unit tests: model tier classification ---

class TestModelTierClassification:
    def test_haiku_is_fast(self) -> None:
        assert classify_model_tier("claude-3-haiku") == "fast"

    def test_sonnet_is_balanced(self) -> None:
        assert classify_model_tier("claude-3-5-sonnet") == "balanced"

    def test_opus_is_powerful(self) -> None:
        assert classify_model_tier("claude-opus-4") == "powerful"

    def test_unknown_model_defaults_to_balanced(self) -> None:
        assert classify_model_tier("unknown-model") == "balanced"


# --- Unit tests: routing optimizer ---

class TestRoutingOptimizer:
    def test_three_tier_routing(self) -> None:
        routing = get_optimal_routing(["claude-opus-4", "claude-3-5-sonnet", "claude-3-haiku"])
        assert routing["simple"] == "claude-3-haiku"
        assert routing["medium"] == "claude-3-5-sonnet"
        assert routing["complex"] == "claude-opus-4"

    def test_two_tier_routing(self) -> None:
        routing = get_optimal_routing(["claude-3-5-sonnet", "claude-3-haiku"])
        assert routing["simple"] == "claude-3-haiku"
        assert routing["medium"] == "claude-3-5-sonnet"

    def test_single_model_routing(self) -> None:
        routing = get_optimal_routing(["claude-3-5-sonnet"])
        assert routing["simple"] == "claude-3-5-sonnet"
        assert routing["medium"] == "claude-3-5-sonnet"

    def test_cheapest_fast_tier_selected(self) -> None:
        routing = get_optimal_routing(["claude-3-haiku", "claude-3-5-haiku", "claude-3-5-sonnet"])
        assert routing["simple"] == "claude-3-haiku"  # cheapest fast tier


# --- Unit tests: cache estimation ---

class TestCacheEstimation:
    def test_no_cache_returns_zero(self) -> None:
        est = estimate_cache_hit_rate(1000, task_diversity=0.5, has_cache=False)
        assert est.estimated_hit_rate == 0.0
        assert est.monthly_cache_savings == 0.0

    def test_low_diversity_high_hit_rate(self) -> None:
        est = estimate_cache_hit_rate(1000, task_diversity=0.2, has_cache=True)
        assert est.estimated_hit_rate >= 0.40

    def test_high_diversity_low_hit_rate(self) -> None:
        est = estimate_cache_hit_rate(1000, task_diversity=0.9, has_cache=True)
        assert est.estimated_hit_rate <= 0.15

    def test_hit_rate_bounded(self) -> None:
        est = estimate_cache_hit_rate(1000, task_diversity=0.0, has_cache=True)
        assert est.estimated_hit_rate <= 0.50
        assert est.estimated_hit_rate >= 0.05


# --- Unit tests: cost projection ---

class TestCostProjection:
    def test_produces_three_scale_levels(self) -> None:
        output = project_costs(["claude-3-5-sonnet"], monthly_tasks=1000)
        assert len(output.projections) == 3
        labels = [p.scale_label for p in output.projections]
        assert labels == ["1x", "10x", "100x"]

    def test_10x_costs_roughly_10x(self) -> None:
        output = project_costs(["claude-3-5-sonnet"], monthly_tasks=1000)
        cost_1x = output.projections[0].total_monthly_cost
        cost_10x = output.projections[1].total_monthly_cost
        ratio = cost_10x / cost_1x if cost_1x > 0 else 0
        assert 9.0 <= ratio <= 11.0

    def test_cache_reduces_effective_cost(self) -> None:
        no_cache = project_costs(["claude-3-5-sonnet"], monthly_tasks=1000, has_cache=False)
        with_cache = project_costs(["claude-3-5-sonnet"], monthly_tasks=1000, has_cache=True, task_diversity=0.3)
        assert with_cache.projections[0].effective_cost < no_cache.projections[0].total_monthly_cost

    def test_three_tier_cheaper_than_single(self) -> None:
        single = project_costs(["claude-opus-4"], monthly_tasks=1000)
        three_tier = project_costs(["claude-opus-4", "claude-3-5-sonnet", "claude-3-haiku"], monthly_tasks=1000)
        assert three_tier.projections[0].effective_cost < single.projections[0].effective_cost

    def test_routing_recommendation_for_single_model(self) -> None:
        output = project_costs(["claude-3-5-sonnet"], monthly_tasks=1000)
        assert "routing" in output.routing_recommendation.lower()

    def test_routing_recommendation_for_three_tier(self) -> None:
        output = project_costs(["claude-opus-4", "claude-3-5-sonnet", "claude-3-haiku"], monthly_tasks=1000)
        assert "optimal" in output.routing_recommendation.lower()


# --- Unit tests: pricing table ---

class TestPricingTable:
    def test_all_models_have_pricing(self) -> None:
        expected = ["claude-3-haiku", "claude-3-5-sonnet", "claude-opus-4"]
        for model in expected:
            assert model in MODEL_PRICING

    def test_haiku_cheapest(self) -> None:
        haiku = MODEL_PRICING["claude-3-haiku"]
        sonnet = MODEL_PRICING["claude-3-5-sonnet"]
        assert haiku.input_per_1m < sonnet.input_per_1m


# --- API endpoint tests ---

async def _signup_and_create_project(client: AsyncClient, email: str, slug: str, models: list[str] | None = None) -> tuple[str, str]:
    signup = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Cost User",
        "tenant_name": "Cost Corp", "tenant_slug": slug,
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Cost Agent", "framework": "langraph",
        "stack_json": {"models": models or ["claude-3-5-sonnet", "claude-3-haiku"], "tools": ["sf"], "deployment": "railway"},
    })
    return token, proj.json()["data"]["id"]


@pytest.mark.asyncio
async def test_cost_projection_endpoint(client: AsyncClient) -> None:
    """Cost projection returns 3 scale levels with model breakdown."""
    token, project_id = await _signup_and_create_project(client, "cost1@test.com", "cost-1")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/cost-projection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["projections"]) == 3
    assert data["projections"][0]["scale_label"] == "1x"
    assert data["projections"][0]["total_monthly_cost"] > 0
    assert data["routing_recommendation"]


@pytest.mark.asyncio
async def test_cost_projection_with_custom_params(client: AsyncClient) -> None:
    """Cost projection accepts custom task volume and distribution."""
    token, project_id = await _signup_and_create_project(client, "cost2@test.com", "cost-2")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/cost-projection",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_tasks": 5000, "simple_pct": 0.70},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["projections"][0]["monthly_tasks"] == 5000


@pytest.mark.asyncio
async def test_pricing_endpoint(client: AsyncClient) -> None:
    """Pricing endpoint returns model pricing table."""
    resp = await client.get("/api/v1/pricing")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 5
    assert any(m["model"] == "claude-3-haiku" for m in data)
