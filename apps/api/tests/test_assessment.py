"""Tests for assessment engine — scorers, runner, and API endpoint."""

import pytest
from httpx import AsyncClient

from app.assessment.runner import AssessmentRunner
from app.assessment.scorers import (
    CostScorer,
    EvalScorer,
    GovernanceScorer,
    ReliabilityScorer,
    SecurityScorer,
)

# --- Unit tests for individual scorers ---

LANGRAPH_STACK = {
    "models": ["claude-3-5-sonnet", "claude-3-haiku"],
    "tools": ["salesforce", "zendesk"],
    "deployment": "railway",
}


class TestReliabilityScorer:
    def test_multi_model_scores_higher(self) -> None:
        scorer = ReliabilityScorer()
        multi = scorer.score({"models": ["sonnet", "haiku"], "deployment": "railway"}, "langraph")
        single = scorer.score({"models": ["sonnet"]}, "custom")
        assert multi.score > single.score

    def test_framework_bonus(self) -> None:
        scorer = ReliabilityScorer()
        langraph = scorer.score(LANGRAPH_STACK, "langraph")
        custom = scorer.score(LANGRAPH_STACK, "custom")
        assert langraph.score > custom.score

    def test_missing_deployment_creates_issue(self) -> None:
        scorer = ReliabilityScorer()
        result = scorer.score({"models": ["sonnet"], "tools": []}, "custom")
        assert any("deployment" in i.title.lower() for i in result.issues)


class TestSecurityScorer:
    def test_no_auth_creates_issue(self) -> None:
        scorer = SecurityScorer()
        result = scorer.score({"models": ["sonnet"]}, "custom")
        assert any("authentication" in i.title.lower() for i in result.issues)

    def test_injection_guard_boosts_score(self) -> None:
        scorer = SecurityScorer()
        guarded = scorer.score({"injection_guard": True}, "custom")
        unguarded = scorer.score({}, "custom")
        assert guarded.score > unguarded.score


class TestEvalScorer:
    def test_no_ci_grader_creates_issue(self) -> None:
        scorer = EvalScorer()
        result = scorer.score({}, "custom")
        assert any("ci grader" in i.title.lower() for i in result.issues)

    def test_high_coverage_scores_better(self) -> None:
        scorer = EvalScorer()
        high = scorer.score({"test_coverage": 85, "ci_grader": True}, "custom")
        low = scorer.score({"test_coverage": 20}, "custom")
        assert high.score > low.score


class TestGovernanceScorer:
    def test_no_audit_trail_creates_issue(self) -> None:
        scorer = GovernanceScorer()
        result = scorer.score({}, "custom")
        assert any("audit" in i.title.lower() for i in result.issues)

    def test_full_governance_scores_high(self) -> None:
        scorer = GovernanceScorer()
        result = scorer.score({
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "alice@acme.ai",
            "compliance_docs": True,
        }, "custom")
        assert result.score >= 90


class TestCostScorer:
    def test_single_model_creates_issue(self) -> None:
        scorer = CostScorer()
        result = scorer.score({"models": ["sonnet"]}, "custom")
        assert any("routing" in i.title.lower() for i in result.issues)

    def test_three_tier_routing_scores_high(self) -> None:
        scorer = CostScorer()
        result = scorer.score({
            "models": ["opus", "sonnet", "haiku"],
            "semantic_cache": True,
            "token_budget": True,
        }, "custom")
        assert result.score >= 90


# --- Integration test for AssessmentRunner ---

class TestAssessmentRunner:
    def test_run_produces_all_five_pillars(self) -> None:
        runner = AssessmentRunner()
        result = runner.run(LANGRAPH_STACK, "langraph")

        assert len(result.pillars) == 5
        assert "reliability" in result.pillars
        assert "security" in result.pillars
        assert "eval" in result.pillars
        assert "governance" in result.pillars
        assert "cost" in result.pillars

    def test_total_score_is_average(self) -> None:
        runner = AssessmentRunner()
        result = runner.run(LANGRAPH_STACK, "langraph")

        expected = round(sum(p.score for p in result.pillars.values()) / 5)
        assert result.total_score == expected

    def test_gap_report_is_non_empty(self) -> None:
        runner = AssessmentRunner()
        result = runner.run(LANGRAPH_STACK, "langraph")

        assert result.gap_report.total_issues > 0
        assert len(result.gap_report.blockers) > 0

    def test_gap_report_sorted_by_severity(self) -> None:
        runner = AssessmentRunner()
        result = runner.run(LANGRAPH_STACK, "langraph")

        severity_order = {"high": 0, "medium": 1, "low": 2}
        severities = [severity_order.get(i.severity, 99) for i in result.gap_report.blockers]
        assert severities == sorted(severities)

    def test_passed_flag_reflects_threshold(self) -> None:
        runner = AssessmentRunner()
        # Minimal config should score below 75
        result = runner.run({"models": ["sonnet"]}, "custom")
        assert result.passed is False


# --- API endpoint tests ---

async def _signup_and_get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Test User",
        "tenant_name": "Test Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_create_project_and_assess(client: AsyncClient) -> None:
    """Full flow: signup → create project → run assessment → verify 5 pillars."""
    token = await _signup_and_get_token(client, "assessor@test.com", "assess-test")
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    project_resp = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Test Agent",
        "framework": "langraph",
        "stack_json": {
            "models": ["claude-3-5-sonnet", "claude-3-haiku"],
            "tools": ["salesforce", "zendesk"],
            "deployment": "railway",
        },
    })
    assert project_resp.status_code == 200
    project_id = project_resp.json()["data"]["id"]

    # Run assessment
    assess_resp = await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
    assert assess_resp.status_code == 200

    data = assess_resp.json()["data"]
    assert data["status"] == "complete"
    assert data["total_score"] > 0
    assert "reliability" in data["scores_json"]
    assert "security" in data["scores_json"]
    assert "eval" in data["scores_json"]
    assert "governance" in data["scores_json"]
    assert "cost" in data["scores_json"]
    assert data["gap_report_json"]["total_issues"] > 0


@pytest.mark.asyncio
async def test_assess_nonexistent_project_returns_404(client: AsyncClient) -> None:
    """Assessment of non-existent project returns 404."""
    token = await _signup_and_get_token(client, "missing@test.com", "missing-test")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/assess",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_project_assess_blocked(client: AsyncClient) -> None:
    """Tenant B cannot assess Tenant A's project."""
    token_a = await _signup_and_get_token(client, "owner-a@test.com", "corp-a")
    token_b = await _signup_and_get_token(client, "owner-b@test.com", "corp-b")

    # Create project as Tenant A
    resp = await client.post("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"}, json={
        "name": "A's Agent", "framework": "custom", "stack_json": {"models": ["sonnet"]},
    })
    project_id = resp.json()["data"]["id"]

    # Try to assess as Tenant B
    assess_resp = await client.post(
        f"/api/v1/projects/{project_id}/assess",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert assess_resp.status_code == 404  # Not visible to tenant B
