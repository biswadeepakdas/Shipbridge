"""Tests for compliance PDF generator — report content, HTML, markdown, API."""

import pytest
from httpx import AsyncClient

from app.governance.pdf import generate_compliance_report


SAMPLE_SCORES = {
    "reliability": {"score": 80, "status": "ok", "issues": [{"title": "Single model", "severity": "medium", "fix_hint": "Add fallback", "evidence": "1 model", "effort_days": 1}], "note": "Good"},
    "security": {"score": 60, "status": "warn", "issues": [{"title": "No injection guard", "severity": "high", "fix_hint": "Add guard", "evidence": "Missing", "effort_days": 2}], "note": "Needs work"},
    "eval": {"score": 75, "status": "ok", "issues": [], "note": "Covered"},
    "governance": {"score": 70, "status": "warn", "issues": [{"title": "No HITL", "severity": "high", "fix_hint": "Add gates", "evidence": "Missing", "effort_days": 3}], "note": "Partial"},
    "cost": {"score": 75, "status": "ok", "issues": [], "note": "Optimized"},
}

SAMPLE_GAP = {
    "blockers": [
        {"title": "No injection guard", "severity": "high", "fix_hint": "Add guard", "effort_days": 2},
        {"title": "No HITL", "severity": "high", "fix_hint": "Add gates", "effort_days": 3},
    ],
    "total_issues": 3,
    "critical_count": 2,
    "estimated_effort_days": 6,
}

SAMPLE_AUDIT = {"total_entries": 45, "actions_by_type": {"tool_call": 30, "hitl_request": 5}, "most_active_agents": []}


# --- Unit tests ---

class TestComplianceReportGeneration:
    def test_generates_report(self) -> None:
        report = generate_compliance_report(
            project_name="Test Agent", tenant_name="Acme Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert report.meta.project_name == "Test Agent"
        assert report.meta.overall_score == 72
        assert report.meta.passed is False

    def test_pillars_populated(self) -> None:
        report = generate_compliance_report(
            project_name="Agent", tenant_name="Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert len(report.pillars) == 5
        names = [p.pillar for p in report.pillars]
        assert "Reliability" in names
        assert "Security" in names

    def test_compliance_checklist_has_20_items(self) -> None:
        report = generate_compliance_report(
            project_name="Agent", tenant_name="Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert len(report.compliance_checklist) == 20

    def test_checklist_has_gdpr_and_soc2(self) -> None:
        report = generate_compliance_report(
            project_name="Agent", tenant_name="Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        categories = {c.category for c in report.compliance_checklist}
        assert "Data Protection" in categories
        assert "Access Control" in categories
        assert "Monitoring" in categories
        assert "Change Management" in categories
        assert "Risk Management" in categories

    def test_markdown_contains_key_sections(self) -> None:
        report = generate_compliance_report(
            project_name="Test Agent", tenant_name="Acme Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert "5-Pillar Scorecard" in report.markdown
        assert "Gap Report" in report.markdown
        assert "Audit Trail Summary" in report.markdown
        assert "GDPR/SOC2" in report.markdown
        assert "72" in report.markdown

    def test_html_is_valid(self) -> None:
        report = generate_compliance_report(
            project_name="Test Agent", tenant_name="Acme Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert report.html.startswith("<!DOCTYPE html>")
        assert "</html>" in report.html
        assert "ShipBridge" in report.html
        assert "72" in report.html

    def test_html_contains_pillar_scores(self) -> None:
        report = generate_compliance_report(
            project_name="Agent", tenant_name="Corp",
            scores_json=SAMPLE_SCORES, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert "Reliability" in report.html
        assert "80" in report.html

    def test_passing_score_shows_ready(self) -> None:
        passing_scores = {k: {**v, "score": 80} for k, v in SAMPLE_SCORES.items()}
        report = generate_compliance_report(
            project_name="Agent", tenant_name="Corp",
            scores_json=passing_scores, gap_report_json=SAMPLE_GAP,
            audit_stats=SAMPLE_AUDIT,
        )
        assert report.meta.passed is True
        assert "PRODUCTION READY" in report.html


# --- API tests ---

async def _setup_project_with_assessment(client: AsyncClient, email: str, slug: str) -> tuple[str, str]:
    """Create a project and run assessment. Returns (token, project_id)."""
    signup = await client.post("/api/v1/auth/signup", json={
        "email": email, "full_name": "PDF User",
        "tenant_name": "PDF Corp", "tenant_slug": slug,
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "PDF Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet", "haiku"], "tools": ["sf"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]
    await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
    return token, project_id


@pytest.mark.asyncio
async def test_generate_pdf_endpoint(client: AsyncClient) -> None:
    token, project_id = await _setup_project_with_assessment(client, "pdf1@test.com", "pdf-1")
    resp = await client.post(f"/api/v1/governance/pdf/{project_id}",
                              headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["meta"]["project_name"] == "PDF Agent"
    assert len(data["pillars"]) == 5
    assert len(data["compliance_checklist"]) == 20
    assert data["markdown"]
    assert data["html"]


@pytest.mark.asyncio
async def test_pdf_html_endpoint(client: AsyncClient) -> None:
    token, project_id = await _setup_project_with_assessment(client, "pdf2@test.com", "pdf-2")
    resp = await client.get(f"/api/v1/governance/pdf/{project_id}/html",
                             headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ShipBridge" in resp.text


@pytest.mark.asyncio
async def test_pdf_without_assessment_returns_404(client: AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json={
        "email": "pdf3@test.com", "full_name": "User",
        "tenant_name": "Corp", "tenant_slug": "pdf-3",
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Empty", "framework": "custom", "stack_json": {},
    })
    project_id = proj.json()["data"]["id"]
    resp = await client.post(f"/api/v1/governance/pdf/{project_id}", headers=headers)
    assert resp.status_code == 404
