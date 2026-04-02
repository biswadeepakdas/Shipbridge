"""Tests for staged deployment workflow — gate, stages, rollback, API."""

import pytest
from httpx import AsyncClient

from app.governance.audit import audit_logger
from app.workers.temporal_workflows import (
    DeployStage,
    DeploymentEngine,
    StageStatus,
    check_auto_rollback,
    check_readiness_gate,
    simulate_stage_metrics,
)


# --- Unit tests: readiness gate ---

class TestReadinessGate:
    def test_passes_at_threshold(self) -> None:
        passed, msg = check_readiness_gate(75)
        assert passed is True

    def test_passes_above_threshold(self) -> None:
        passed, _ = check_readiness_gate(90)
        assert passed is True

    def test_blocks_below_threshold(self) -> None:
        passed, msg = check_readiness_gate(74)
        assert passed is False
        assert "below" in msg.lower()

    def test_blocks_at_zero(self) -> None:
        passed, _ = check_readiness_gate(0)
        assert passed is False


# --- Unit tests: stage metrics ---

class TestStageMetrics:
    def test_sandbox_metrics(self) -> None:
        m = simulate_stage_metrics(DeployStage.SANDBOX)
        assert m.task_success_rate > 0.9
        assert m.latency_p95_ms > 0

    def test_regression_injection(self) -> None:
        normal = simulate_stage_metrics(DeployStage.CANARY_5)
        regressed = simulate_stage_metrics(DeployStage.CANARY_5, inject_regression=True)
        assert regressed.task_success_rate < normal.task_success_rate
        assert regressed.error_rate > normal.error_rate


# --- Unit tests: auto-rollback ---

class TestAutoRollback:
    def test_no_rollback_within_range(self) -> None:
        baseline = simulate_stage_metrics(DeployStage.SANDBOX)
        current = simulate_stage_metrics(DeployStage.CANARY_5)
        should, _ = check_auto_rollback(baseline, current)
        assert should is False

    def test_rollback_on_regression(self) -> None:
        baseline = simulate_stage_metrics(DeployStage.SANDBOX)
        regressed = simulate_stage_metrics(DeployStage.CANARY_5, inject_regression=True)
        should, reason = check_auto_rollback(baseline, regressed)
        assert should is True
        assert "dropped" in reason.lower()

    def test_no_rollback_without_baseline(self) -> None:
        current = simulate_stage_metrics(DeployStage.CANARY_5)
        should, _ = check_auto_rollback(None, current)
        assert should is False


# --- Unit tests: deployment engine ---

class TestDeploymentEngine:
    def setup_method(self) -> None:
        audit_logger.clear()

    def test_create_workflow_with_passing_score(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=80)
        assert wf.status == "running"
        assert wf.current_stage == DeployStage.SANDBOX
        assert len(wf.stages) == 4
        assert wf.stages[0].status == StageStatus.ACTIVE

    def test_create_workflow_blocked_by_gate(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=50)
        assert wf.status == "failed"
        assert wf.current_stage is None

    def test_advance_through_stages(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=80)

        # Advance sandbox → canary5
        wf = engine.advance_stage(wf.id)
        assert wf.current_stage == DeployStage.CANARY_5
        assert wf.stages[0].status == StageStatus.COMPLETE

        # Advance canary5 → canary25
        wf = engine.advance_stage(wf.id)
        assert wf.current_stage == DeployStage.CANARY_25

        # Advance canary25 → production
        wf = engine.advance_stage(wf.id)
        assert wf.current_stage == DeployStage.PRODUCTION

        # Advance production → complete
        wf = engine.advance_stage(wf.id)
        assert wf.status == "complete"

    def test_full_4_stage_pipeline(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=85)
        for _ in range(4):
            wf = engine.advance_stage(wf.id)
        assert wf.status == "complete"
        assert all(s.status == StageStatus.COMPLETE for s in wf.stages)

    def test_rollback_on_regression(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=80)

        # Advance sandbox (collects baseline)
        wf = engine.advance_stage(wf.id)

        # Advance canary5 with regression
        wf = engine.advance_stage(wf.id, inject_regression=True)
        assert wf.status == "rolled_back"
        rolled_back_stage = next(s for s in wf.stages if s.status == StageStatus.ROLLED_BACK)
        assert rolled_back_stage.name == DeployStage.CANARY_5  # active when regression detected

    def test_deployment_creates_audit_entries(self) -> None:
        engine = DeploymentEngine()
        wf = engine.create_workflow("p1", "t1", readiness_score=80)
        entries = audit_logger.query("t1")
        assert len(entries) >= 1
        assert any("workflow_started" in str(e.details) for e in entries)

    def test_list_workflows(self) -> None:
        engine = DeploymentEngine()
        engine.create_workflow("p1", "t1", readiness_score=80)
        engine.create_workflow("p2", "t1", readiness_score=90)
        engine.create_workflow("p3", "t2", readiness_score=80)
        assert len(engine.list_workflows("t1")) == 2
        assert len(engine.list_workflows("t2")) == 1


# --- API endpoint tests ---

@pytest.fixture(autouse=True)
def _reset() -> None:
    from app.workers.temporal_workflows import deployment_engine
    deployment_engine.clear()
    audit_logger.clear()


async def _create_assessed_project(client: AsyncClient, email: str, slug: str) -> tuple[str, str]:
    """Signup, create project, run assessment. Returns (token, project_id)."""
    signup = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Deploy User",
        "tenant_name": "Deploy Corp", "tenant_slug": slug,
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Deploy Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet", "haiku"], "tools": ["sf"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]
    await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
    return token, project_id


@pytest.mark.asyncio
async def test_trigger_deployment(client: AsyncClient) -> None:
    token, project_id = await _create_assessed_project(client, "dep1@test.com", "dep-1")
    resp = await client.post("/api/v1/deployments",
        headers={"Authorization": f"Bearer {token}"},
        json={"project_id": project_id},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] in ("running", "failed")


@pytest.mark.asyncio
async def test_advance_deployment_stage(client: AsyncClient) -> None:
    token, project_id = await _create_assessed_project(client, "dep2@test.com", "dep-2")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post("/api/v1/deployments", headers=headers,
                                     json={"project_id": project_id})
    dep_id = create_resp.json()["data"]["id"]

    if create_resp.json()["data"]["status"] == "running":
        advance_resp = await client.post(f"/api/v1/deployments/{dep_id}/advance", headers=headers)
        assert advance_resp.status_code == 200


@pytest.mark.asyncio
async def test_get_deployment_stages(client: AsyncClient) -> None:
    token, project_id = await _create_assessed_project(client, "dep3@test.com", "dep-3")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post("/api/v1/deployments", headers=headers,
                                     json={"project_id": project_id})
    dep_id = create_resp.json()["data"]["id"]

    stages_resp = await client.get(f"/api/v1/deployments/{dep_id}/stages", headers=headers)
    assert stages_resp.status_code == 200
    stages = stages_resp.json()["data"]
    assert len(stages) == 4 or stages == []  # 4 if running, empty if gate blocked


@pytest.mark.asyncio
async def test_list_deployments(client: AsyncClient) -> None:
    token, project_id = await _create_assessed_project(client, "dep4@test.com", "dep-4")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/deployments", headers=headers, json={"project_id": project_id})
    resp = await client.get("/api/v1/deployments", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1
