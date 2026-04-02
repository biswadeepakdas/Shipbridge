"""Tests for governance — audit logger, HITL gates, API endpoints."""

import pytest
from httpx import AsyncClient

from app.governance.audit import AuditAction, AuditLogger
from app.governance.hitl import GateCondition, GateManager, GateStatus


# --- Unit tests: AuditLogger ---

class TestAuditLogger:
    def test_log_creates_entry(self) -> None:
        al = AuditLogger()
        entry = al.log(tenant_id="t1", action=AuditAction.TOOL_CALL,
                       resource_type="connector", resource_id="c1")
        assert entry.action == AuditAction.TOOL_CALL
        assert entry.tenant_id == "t1"
        assert al.total_entries == 1

    def test_entries_are_immutable_append(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="a")
        al.log(tenant_id="t1", action=AuditAction.LLM_DECISION, resource_type="b")
        assert al.total_entries == 2

    def test_query_by_tenant(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="a")
        al.log(tenant_id="t2", action=AuditAction.TOOL_CALL, resource_type="b")
        assert len(al.query("t1")) == 1
        assert len(al.query("t2")) == 1

    def test_query_by_action(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="a")
        al.log(tenant_id="t1", action=AuditAction.AUTH_EVENT, resource_type="b")
        results = al.query("t1", action=AuditAction.TOOL_CALL)
        assert len(results) == 1

    def test_query_by_resource_type(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="connector")
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="project")
        results = al.query("t1", resource_type="connector")
        assert len(results) == 1

    def test_query_returns_newest_first(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="first")
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="second")
        results = al.query("t1")
        assert results[0].resource_type == "second"

    def test_stats(self) -> None:
        al = AuditLogger()
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="a", agent_id="ag1")
        al.log(tenant_id="t1", action=AuditAction.TOOL_CALL, resource_type="b", agent_id="ag1")
        al.log(tenant_id="t1", action=AuditAction.AUTH_EVENT, resource_type="c")
        stats = al.get_stats("t1")
        assert stats.total_entries == 3
        assert stats.actions_by_type["tool_call"] == 2
        assert stats.most_active_agents[0]["agent_id"] == "ag1"


# --- Unit tests: HITL GateManager ---

class TestGateManager:
    def test_create_gate(self) -> None:
        gm = GateManager()
        gate = gm.create_gate(
            tenant_id="t1", title="Deploy to prod",
            description="Requires approval", requested_by="agent-1",
            resource_type="deployment", risk_level="critical",
        )
        assert gate.status == GateStatus.PENDING
        assert gate.title == "Deploy to prod"

    def test_approve_gate(self) -> None:
        gm = GateManager()
        gate = gm.create_gate(tenant_id="t1", title="Test", description="desc",
                              requested_by="ag1", resource_type="deploy")
        approved = gm.approve(gate.id, approved_by="user-1", note="LGTM")
        assert approved is not None
        assert approved.status == GateStatus.APPROVED
        assert approved.resolved_by == "user-1"

    def test_reject_gate(self) -> None:
        gm = GateManager()
        gate = gm.create_gate(tenant_id="t1", title="Test", description="desc",
                              requested_by="ag1", resource_type="deploy")
        rejected = gm.reject(gate.id, rejected_by="user-1", note="Too risky")
        assert rejected is not None
        assert rejected.status == GateStatus.REJECTED

    def test_cannot_approve_already_resolved(self) -> None:
        gm = GateManager()
        gate = gm.create_gate(tenant_id="t1", title="Test", description="d",
                              requested_by="ag1", resource_type="x")
        gm.approve(gate.id, "u1")
        assert gm.approve(gate.id, "u2") is None  # already resolved

    def test_list_pending(self) -> None:
        gm = GateManager()
        gm.create_gate(tenant_id="t1", title="G1", description="d", requested_by="ag1", resource_type="x")
        g2 = gm.create_gate(tenant_id="t1", title="G2", description="d", requested_by="ag1", resource_type="x")
        gm.approve(g2.id, "u1")
        pending = gm.list_pending("t1")
        assert len(pending) == 1
        assert pending[0].title == "G1"

    def test_should_gate_matches(self) -> None:
        gm = GateManager()
        gm.add_condition(GateCondition(resource_type="deployment", action_pattern="deploy.*"))
        assert gm.should_gate("deployment", "deploy.production") is not None
        assert gm.should_gate("connector", "connect") is None

    def test_gate_creates_audit_entries(self) -> None:
        from app.governance.audit import audit_logger
        audit_logger.clear()
        gm = GateManager()
        gate = gm.create_gate(tenant_id="t1", title="Audit test", description="d",
                              requested_by="ag1", resource_type="deploy")
        gm.approve(gate.id, "user-1")
        entries = audit_logger.query("t1")
        actions = [e.action.value for e in entries]
        assert "hitl_request" in actions
        assert "hitl_response" in actions

    def test_tenant_isolation(self) -> None:
        gm = GateManager()
        gm.create_gate(tenant_id="t1", title="T1 gate", description="d",
                       requested_by="ag1", resource_type="x")
        gm.create_gate(tenant_id="t2", title="T2 gate", description="d",
                       requested_by="ag2", resource_type="x")
        assert len(gm.list_all("t1")) == 1
        assert len(gm.list_all("t2")) == 1


# --- API endpoint tests ---

@pytest.fixture(autouse=True)
def _reset() -> None:
    from app.governance.audit import audit_logger
    from app.governance.hitl import gate_manager
    audit_logger.clear()
    gate_manager.clear()


async def _get_token(client: AsyncClient, email: str, slug: str) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "Gov User",
        "tenant_name": "Gov Corp", "tenant_slug": slug,
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_audit_log_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client, "gov1@test.com", "gov-1")
    headers = {"Authorization": f"Bearer {token}"}
    # Create a gate to generate audit entries
    await client.post("/api/v1/governance/gates", headers=headers, json={
        "title": "Test gate", "description": "desc", "resource_type": "deploy",
    })
    resp = await client.get("/api/v1/governance/audit", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1


@pytest.mark.asyncio
async def test_audit_stats_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client, "gov2@test.com", "gov-2")
    resp = await client.get("/api/v1/governance/audit/stats",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "total_entries" in resp.json()["data"]


@pytest.mark.asyncio
async def test_create_and_approve_gate(client: AsyncClient) -> None:
    token = await _get_token(client, "gov3@test.com", "gov-3")
    headers = {"Authorization": f"Bearer {token}"}

    # Create gate
    create_resp = await client.post("/api/v1/governance/gates", headers=headers, json={
        "title": "Deploy to production", "description": "Requires human approval",
        "resource_type": "deployment", "risk_level": "critical",
    })
    assert create_resp.status_code == 200
    gate_id = create_resp.json()["data"]["id"]
    assert create_resp.json()["data"]["status"] == "pending"

    # Approve
    approve_resp = await client.post(f"/api/v1/governance/gates/{gate_id}/approve",
                                      headers=headers, json={"note": "Approved for deploy"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "approved"


@pytest.mark.asyncio
async def test_create_and_reject_gate(client: AsyncClient) -> None:
    token = await _get_token(client, "gov4@test.com", "gov-4")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post("/api/v1/governance/gates", headers=headers, json={
        "title": "Risky change", "description": "Needs review",
        "resource_type": "config", "risk_level": "high",
    })
    gate_id = create_resp.json()["data"]["id"]

    reject_resp = await client.post(f"/api/v1/governance/gates/{gate_id}/reject",
                                     headers=headers, json={"note": "Too risky"})
    assert reject_resp.json()["data"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_list_pending_gates(client: AsyncClient) -> None:
    token = await _get_token(client, "gov5@test.com", "gov-5")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/governance/gates", headers=headers, json={
        "title": "G1", "description": "d", "resource_type": "x"})
    await client.post("/api/v1/governance/gates", headers=headers, json={
        "title": "G2", "description": "d", "resource_type": "x"})

    resp = await client.get("/api/v1/governance/gates?status=pending", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2
