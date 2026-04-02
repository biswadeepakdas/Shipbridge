"""Tests for onboarding — wizard steps, framework options, quick-start API."""

import pytest
from httpx import AsyncClient

from app.services.onboarding import (
    get_framework_options,
    get_onboarding_steps,
    get_sample_config,
    run_onboarding_assessment,
)


# --- Unit tests ---

class TestOnboardingService:
    def test_get_steps(self) -> None:
        steps = get_onboarding_steps()
        assert len(steps) == 4
        assert steps[0].title == "Name your project"
        assert steps[3].title == "First assessment"

    def test_get_framework_options(self) -> None:
        options = get_framework_options()
        assert len(options) == 5
        names = [o["id"] for o in options]
        assert "langraph" in names
        assert "crewai" in names
        assert "custom" in names

    def test_sample_config_langraph(self) -> None:
        config = get_sample_config("langraph")
        assert "models" in config
        assert len(config["models"]) >= 2

    def test_sample_config_custom_fallback(self) -> None:
        config = get_sample_config("unknown_framework")
        assert config == get_sample_config("custom")

    def test_onboarding_assessment_returns_result(self) -> None:
        config = get_sample_config("langraph")
        result = run_onboarding_assessment(config, "langraph")
        assert result.assessment_score > 0
        assert len(result.next_steps) > 0

    def test_onboarding_assessment_generates_next_steps(self) -> None:
        config = get_sample_config("custom")
        result = run_onboarding_assessment(config, "custom")
        assert len(result.next_steps) >= 2
        # Should include connector suggestion
        assert any("connect" in s.lower() for s in result.next_steps)

    def test_passing_assessment_shows_ready(self) -> None:
        config = {
            "models": ["opus", "sonnet", "haiku"],
            "tools": ["sf", "slack"],
            "deployment": "railway",
            "auth": {"type": "oauth2"},
            "injection_guard": True,
            "ci_grader": True,
            "test_coverage": 90,
            "eval_baseline": True,
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "alice",
            "semantic_cache": True,
            "token_budget": True,
        }
        result = run_onboarding_assessment(config, "langraph")
        assert result.assessment_passed is True
        assert any("ready" in s.lower() for s in result.next_steps)


# --- API tests ---

async def _get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Onboard User",
        "tenant_name": "Onboard Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_get_steps_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/onboarding/steps")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 4


@pytest.mark.asyncio
async def test_get_frameworks_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/onboarding/frameworks")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 5


@pytest.mark.asyncio
async def test_sample_config_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/onboarding/sample-config/langraph")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["framework"] == "langraph"
    assert "models" in data["stack_json"]


@pytest.mark.asyncio
async def test_quick_start_creates_project_and_assessment(client: AsyncClient) -> None:
    token = await _get_token(client, "onboard1@test.com", "onboard-1")
    resp = await client.post("/api/v1/onboarding/quick-start",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_name": "My First Agent", "framework": "langraph"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project_name"] == "My First Agent"
    assert data["framework"] == "langraph"
    assert data["assessment_score"] > 0
    assert len(data["next_steps"]) > 0
    assert data["project_id"]  # non-empty


@pytest.mark.asyncio
async def test_quick_start_with_custom_config(client: AsyncClient) -> None:
    token = await _get_token(client, "onboard2@test.com", "onboard-2")
    resp = await client.post("/api/v1/onboarding/quick-start",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_name": "Custom Agent",
            "framework": "custom",
            "stack_json": {"models": ["sonnet"], "tools": ["slack"]},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["framework"] == "custom"
