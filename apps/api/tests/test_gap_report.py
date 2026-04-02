"""Tests for gap report, readiness gate, SSE stream, and drill-down endpoints."""

import json

import pytest
from httpx import AsyncClient

from app.assessment.readiness_gate import evaluate_readiness
from app.assessment.runner import AssessmentRunner


# --- Unit tests for ReadinessGate ---

class TestReadinessGate:
    def test_passing_score_allows_deploy(self) -> None:
        runner = AssessmentRunner()
        result = runner.run({
            "models": ["opus", "sonnet", "haiku"],
            "tools": ["sf", "slack"],
            "deployment": "railway",
            "auth": {"type": "oauth2"},
            "injection_guard": True,
            "ci_grader": True,
            "test_coverage": 90,
            "eval_baseline": True,
            "eval_dataset": True,
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "alice",
            "compliance_docs": True,
            "semantic_cache": True,
            "token_budget": True,
        }, "langraph")
        readiness = evaluate_readiness(result)
        assert readiness.can_deploy is True
        assert readiness.gap == 0
        assert len(readiness.steps) == 0

    def test_failing_score_blocks_deploy(self) -> None:
        runner = AssessmentRunner()
        result = runner.run({"models": ["sonnet"]}, "custom")
        readiness = evaluate_readiness(result)
        assert readiness.can_deploy is False
        assert readiness.gap > 0
        assert len(readiness.steps) > 0
        assert readiness.estimated_total_days > 0

    def test_remediation_steps_ordered_by_worst_pillar(self) -> None:
        runner = AssessmentRunner()
        result = runner.run({"models": ["sonnet"]}, "custom")
        readiness = evaluate_readiness(result)
        # Steps should start from lowest-scoring pillar
        if len(readiness.steps) >= 2:
            first_pillar = readiness.steps[0].pillar
            first_score = result.pillars[first_pillar].score
            # Verify it's from one of the lowest-scoring pillars
            min_score = min(p.score for p in result.pillars.values())
            assert first_score == min_score


# --- API endpoint tests ---

async def _signup_and_get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Test User",
        "tenant_name": "Test Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


async def _create_project_and_assess(client: AsyncClient, token: str) -> tuple[str, str]:
    """Helper: create project and run assessment. Returns (project_id, run_id)."""
    headers = {"Authorization": f"Bearer {token}"}
    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Test Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet", "haiku"], "tools": ["sf"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]
    assess = await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
    run_id = assess.json()["data"]["id"]
    return project_id, run_id


@pytest.mark.asyncio
async def test_readiness_gate_endpoint(client: AsyncClient) -> None:
    """Readiness gate returns deployment status after assessment."""
    token = await _signup_and_get_token(client, "gate@test.com", "gate-test")
    project_id, _ = await _create_project_and_assess(client, token)

    resp = await client.get(
        f"/api/v1/projects/{project_id}/readiness",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "can_deploy" in data
    assert data["target_score"] == 75
    assert data["current_score"] > 0


@pytest.mark.asyncio
async def test_readiness_without_assessment_returns_404(client: AsyncClient) -> None:
    """Readiness check without prior assessment returns 404."""
    token = await _signup_and_get_token(client, "noassess@test.com", "noassess-test")
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Empty Agent", "framework": "custom", "stack_json": {},
    })
    project_id = proj.json()["data"]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/readiness", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sse_stream_returns_events(client: AsyncClient) -> None:
    """SSE stream returns pillar_scored events followed by assessment_complete."""
    token = await _signup_and_get_token(client, "stream@test.com", "stream-test")
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Stream Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet"], "tools": ["sf"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]

    resp = await client.get(
        f"/api/v1/projects/{project_id}/assess/stream",
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # Parse SSE events
    events = []
    for line in resp.text.strip().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    # Should have 5 pillar events + 1 complete event
    assert len(events) == 6
    pillar_events = [e for e in events if e["event"] == "pillar_scored"]
    assert len(pillar_events) == 5

    complete_event = [e for e in events if e["event"] == "assessment_complete"]
    assert len(complete_event) == 1
    assert complete_event[0]["total_score"] > 0
    assert "can_deploy" in complete_event[0]


@pytest.mark.asyncio
async def test_assessment_stores_gap_report_with_issues(client: AsyncClient) -> None:
    """Assessment run stores gap report with non-empty blockers list."""
    token = await _signup_and_get_token(client, "gap@test.com", "gap-test")
    project_id, _ = await _create_project_and_assess(client, token)

    resp = await client.get(
        f"/api/v1/projects/{project_id}/assessments",
        headers={"Authorization": f"Bearer {token}"},
    )
    runs = resp.json()["data"]
    assert len(runs) >= 1
    gap = runs[0]["gap_report_json"]
    assert gap["total_issues"] > 0
    assert len(gap["blockers"]) > 0
    # Each blocker has required fields
    for blocker in gap["blockers"]:
        assert "title" in blocker
        assert "evidence" in blocker
        assert "fix_hint" in blocker
        assert "severity" in blocker
        assert "effort_days" in blocker
