"""Tests for eval harness — dataset generation, grader, CI gate, baseline, and API."""

import pytest
from httpx import AsyncClient

from app.services.eval_harness import (
    capture_baseline,
    generate_ci_gate_template,
    generate_dataset,
    generate_eval_harness,
    generate_grader_template,
)


# --- Unit tests: dataset generation ---

class TestDatasetGeneration:
    def test_generates_correct_count(self) -> None:
        ds = generate_dataset("Test Agent", "langraph", ["salesforce"], num_cases=20)
        assert ds.total_cases == 20
        assert len(ds.test_cases) == 20

    def test_includes_tool_specific_cases(self) -> None:
        ds = generate_dataset("Agent", "custom", ["slack", "hubspot"], num_cases=20)
        tool_cases = [tc for tc in ds.test_cases if tc.category == "tool_integration"]
        assert len(tool_cases) >= 2
        texts = " ".join(tc.input_text for tc in tool_cases)
        assert "slack" in texts.lower()
        assert "hubspot" in texts.lower()

    def test_uses_framework_templates(self) -> None:
        ds = generate_dataset("CrewAgent", "crewai", [], num_cases=10)
        categories = {tc.category for tc in ds.test_cases}
        assert "delegation" in categories or "collaboration" in categories

    def test_default_templates_for_unknown_framework(self) -> None:
        ds = generate_dataset("Unknown", "custom", [], num_cases=10)
        categories = {tc.category for tc in ds.test_cases}
        assert "basic_response" in categories

    def test_each_case_has_required_fields(self) -> None:
        ds = generate_dataset("Agent", "langraph", ["sf"], num_cases=10)
        for tc in ds.test_cases:
            assert tc.id
            assert tc.input_text
            assert tc.expected_behavior
            assert tc.category
            assert tc.difficulty in ("easy", "medium", "hard")


# --- Unit tests: grader template ---

class TestGraderTemplate:
    def test_grader_uses_haiku(self) -> None:
        grader = generate_grader_template("langraph")
        assert "haiku" in grader.model

    def test_grader_has_scoring_rubric(self) -> None:
        grader = generate_grader_template("custom")
        assert "correctness" in grader.scoring_rubric
        assert "completeness" in grader.scoring_rubric
        assert "safety" in grader.scoring_rubric
        assert "efficiency" in grader.scoring_rubric

    def test_grader_has_pass_threshold(self) -> None:
        grader = generate_grader_template("langraph")
        assert grader.pass_threshold > 0
        assert grader.output_format == "json"

    def test_grader_prompt_has_placeholders(self) -> None:
        grader = generate_grader_template("custom")
        assert "{input_text}" in grader.prompt_template
        assert "{expected_behavior}" in grader.prompt_template
        assert "{agent_output}" in grader.prompt_template


# --- Unit tests: CI gate ---

class TestCIGateTemplate:
    def test_generates_valid_yaml(self) -> None:
        gate = generate_ci_gate_template("My Agent", threshold=80)
        assert "name: ShipBridge Eval Gate" in gate.yaml_content
        assert "80" in gate.yaml_content
        assert gate.score_threshold == 80

    def test_filename_is_correct(self) -> None:
        gate = generate_ci_gate_template("Agent")
        assert gate.filename == ".github/workflows/shipbridge-eval-gate.yml"

    def test_uses_secrets(self) -> None:
        gate = generate_ci_gate_template("Agent")
        assert "SHIPBRIDGE_API_KEY" in gate.yaml_content
        assert "SHIPBRIDGE_PROJECT_ID" in gate.yaml_content


# --- Unit tests: baseline ---

class TestBaseline:
    def test_baseline_has_scores(self) -> None:
        ds = generate_dataset("Agent", "langraph", ["sf"], num_cases=10)
        baseline = capture_baseline(ds)
        assert len(baseline.scores) > 0
        assert baseline.pass_rate > 0
        assert baseline.total_cases == 10

    def test_baseline_captures_timestamp(self) -> None:
        ds = generate_dataset("Agent", "custom", [], num_cases=5)
        baseline = capture_baseline(ds)
        assert baseline.captured_at


# --- Unit tests: full harness ---

class TestEvalHarness:
    def test_generates_complete_harness(self) -> None:
        harness = generate_eval_harness("Agent", "langraph", ["sf", "slack"], num_cases=15)
        assert harness.dataset.total_cases == 15
        assert harness.grader.model
        assert harness.ci_gate.yaml_content
        assert harness.baseline.pass_rate > 0

    def test_harness_respects_threshold(self) -> None:
        harness = generate_eval_harness("Agent", "custom", [], threshold=90)
        assert harness.ci_gate.score_threshold == 90


# --- API endpoint tests ---

async def _signup_and_create_project(client: AsyncClient, email: str, slug: str) -> tuple[str, str]:
    """Helper: signup and create a project. Returns (token, project_id)."""
    signup = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Eval User",
        "tenant_name": "Eval Corp", "tenant_slug": slug,
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Eval Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet", "haiku"], "tools": ["salesforce", "slack"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]
    return token, project_id


@pytest.mark.asyncio
async def test_generate_eval_harness_endpoint(client: AsyncClient) -> None:
    """Generate eval harness returns complete output with dataset, grader, CI gate."""
    token, project_id = await _signup_and_create_project(client, "eval1@test.com", "eval-1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(f"/api/v1/projects/{project_id}/eval/generate", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dataset"]["total_cases"] == 20
    assert data["grader"]["model"]
    assert "yaml_content" in data["ci_gate"]
    assert data["baseline"]["pass_rate"] > 0


@pytest.mark.asyncio
async def test_eval_run_stored_after_generate(client: AsyncClient) -> None:
    """Generating harness stores an eval run and baseline in DB."""
    token, project_id = await _signup_and_create_project(client, "eval2@test.com", "eval-2")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(f"/api/v1/projects/{project_id}/eval/generate", headers=headers)

    # Check eval runs
    runs_resp = await client.get(f"/api/v1/projects/{project_id}/eval/runs", headers=headers)
    assert runs_resp.status_code == 200
    runs = runs_resp.json()["data"]
    assert len(runs) >= 1
    assert runs[0]["status"] == "complete"
    assert runs[0]["pass_rate"] == 80

    # Check baseline
    baseline_resp = await client.get(f"/api/v1/projects/{project_id}/eval/baseline", headers=headers)
    assert baseline_resp.status_code == 200
    baseline = baseline_resp.json()["data"]
    assert baseline is not None
    assert baseline["is_active"] is True


@pytest.mark.asyncio
async def test_ci_gate_download(client: AsyncClient) -> None:
    """CI gate endpoint returns downloadable YAML template."""
    token, project_id = await _signup_and_create_project(client, "eval3@test.com", "eval-3")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/projects/{project_id}/eval/ci-gate", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "yaml_content" in data
    assert "shipbridge-eval-gate.yml" in data["filename"]


@pytest.mark.asyncio
async def test_baseline_none_before_generate(client: AsyncClient) -> None:
    """Baseline is null before any eval harness is generated."""
    token, project_id = await _signup_and_create_project(client, "eval4@test.com", "eval-4")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/projects/{project_id}/eval/baseline", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None
