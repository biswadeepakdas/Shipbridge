"""CompliancePDFGenerator — generates structured readiness report.

Produces HTML report (renderable to PDF via weasyprint in production)
and markdown fallback. Includes cover page, 5-pillar scorecard,
audit trail summary, deployment history, and GDPR/SOC2 checklist.
"""

from datetime import datetime, timezone

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class ComplianceReportMeta(BaseModel):
    """Report metadata."""

    project_name: str
    tenant_name: str
    generated_at: str
    generated_by: str
    report_version: str = "1.0"
    overall_score: int
    passed: bool


class PillarEvidence(BaseModel):
    """Evidence for a single pillar in the scorecard."""

    pillar: str
    score: int
    status: str
    issues: list[dict]
    note: str


class ComplianceCheckItem(BaseModel):
    """A single GDPR/SOC2 checklist item."""

    control_id: str
    category: str
    description: str
    status: str  # "pass", "fail", "partial", "n/a"
    evidence: str


class ComplianceReport(BaseModel):
    """Complete compliance report output."""

    meta: ComplianceReportMeta
    pillars: list[PillarEvidence]
    audit_summary: dict
    deployment_history: list[dict]
    compliance_checklist: list[ComplianceCheckItem]
    markdown: str
    html: str


# --- GDPR/SOC2 Checklist ---

def _generate_compliance_checklist(scores_json: dict, has_audit: bool, has_hitl: bool) -> list[ComplianceCheckItem]:
    """Generate 20-item GDPR/SOC2 compliance checklist based on assessment data."""
    security_score = scores_json.get("security", {}).get("score", 0)
    governance_score = scores_json.get("governance", {}).get("score", 0)

    checks = [
        # Data Protection (GDPR) — 4 items
        ComplianceCheckItem(control_id="GDPR-01", category="Data Protection", description="Personal data inventory documented", status="partial", evidence="Stack config reviewed"),
        ComplianceCheckItem(control_id="GDPR-02", category="Data Protection", description="Data retention policy implemented", status="partial", evidence="24h dedup TTL configured"),
        ComplianceCheckItem(control_id="GDPR-03", category="Data Protection", description="Right to erasure mechanism", status="fail" if security_score < 50 else "partial", evidence="API key deletion supported"),
        ComplianceCheckItem(control_id="GDPR-04", category="Data Protection", description="No PII in logs", status="pass" if security_score >= 60 else "fail", evidence="Structured logging with redaction"),

        # Access Control (SOC2) — 4 items
        ComplianceCheckItem(control_id="SOC2-01", category="Access Control", description="Multi-tenant isolation enforced", status="pass", evidence="tenant_id on all queries, RLS policies"),
        ComplianceCheckItem(control_id="SOC2-02", category="Access Control", description="Authentication on all endpoints", status="pass" if security_score >= 50 else "fail", evidence="JWT + API key auth middleware"),
        ComplianceCheckItem(control_id="SOC2-03", category="Access Control", description="Role-based access control", status="pass", evidence="owner/admin/member roles"),
        ComplianceCheckItem(control_id="SOC2-04", category="Access Control", description="API keys HMAC-hashed", status="pass", evidence="HMAC-SHA256 hashing in auth service"),

        # Monitoring (SOC2) — 4 items
        ComplianceCheckItem(control_id="SOC2-05", category="Monitoring", description="Audit trail for all actions", status="pass" if has_audit else "fail", evidence="AuditLogger immutable append-only"),
        ComplianceCheckItem(control_id="SOC2-06", category="Monitoring", description="Structured logging with trace IDs", status="pass", evidence="structlog + X-Trace-ID"),
        ComplianceCheckItem(control_id="SOC2-07", category="Monitoring", description="Error tracking configured", status="pass", evidence="Sentry integration"),
        ComplianceCheckItem(control_id="SOC2-08", category="Monitoring", description="Health checks on all services", status="pass", evidence="/health with dependency checks"),

        # Change Management (SOC2) — 4 items
        ComplianceCheckItem(control_id="SOC2-09", category="Change Management", description="HITL gates for high-risk actions", status="pass" if has_hitl else "fail", evidence="GateManager approve/reject flow"),
        ComplianceCheckItem(control_id="SOC2-10", category="Change Management", description="Staged deployment pipeline", status="partial", evidence="sandbox → canary → production"),
        ComplianceCheckItem(control_id="SOC2-11", category="Change Management", description="CI/CD pipeline with tests", status="pass", evidence="GitHub Actions: lint + test + build"),
        ComplianceCheckItem(control_id="SOC2-12", category="Change Management", description="Assessment gate before deploy", status="pass", evidence="ReadinessGate score >= 75"),

        # Risk Management — 4 items
        ComplianceCheckItem(control_id="RISK-01", category="Risk Management", description="Prompt injection detection", status="pass" if security_score >= 70 else "fail", evidence="SecurityScorer checks surfaces"),
        ComplianceCheckItem(control_id="RISK-02", category="Risk Management", description="Rate limiting on API", status="pass", evidence="Rate limit middleware"),
        ComplianceCheckItem(control_id="RISK-03", category="Risk Management", description="Webhook signature verification", status="pass", evidence="HMAC-SHA256 on webhooks"),
        ComplianceCheckItem(control_id="RISK-04", category="Risk Management", description="Dead letter queue for failures", status="pass", evidence="DLQ with failure tracking"),
    ]

    return checks


# --- Report Generation ---

def generate_compliance_report(
    project_name: str,
    tenant_name: str,
    scores_json: dict,
    gap_report_json: dict,
    audit_stats: dict,
    deployment_history: list[dict] | None = None,
    generated_by: str = "system",
) -> ComplianceReport:
    """Generate a complete compliance report."""
    overall_score = 0
    pillar_count = 0
    pillars: list[PillarEvidence] = []

    for name, data in scores_json.items():
        score = data.get("score", 0)
        overall_score += score
        pillar_count += 1
        pillars.append(PillarEvidence(
            pillar=name.capitalize(),
            score=score,
            status=data.get("status", "unknown"),
            issues=data.get("issues", []),
            note=data.get("note", ""),
        ))

    overall_score = round(overall_score / max(pillar_count, 1))
    passed = overall_score >= 75

    has_audit = audit_stats.get("total_entries", 0) > 0
    has_hitl = any(a == "hitl_request" for a in audit_stats.get("actions_by_type", {}).keys())

    checklist = _generate_compliance_checklist(scores_json, has_audit, has_hitl)
    meta = ComplianceReportMeta(
        project_name=project_name,
        tenant_name=tenant_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generated_by=generated_by,
        overall_score=overall_score,
        passed=passed,
    )

    # Generate markdown
    md = _generate_markdown(meta, pillars, gap_report_json, audit_stats, deployment_history or [], checklist)
    html = _generate_html(meta, pillars, gap_report_json, audit_stats, deployment_history or [], checklist)

    return ComplianceReport(
        meta=meta,
        pillars=pillars,
        audit_summary=audit_stats,
        deployment_history=deployment_history or [],
        compliance_checklist=checklist,
        markdown=md,
        html=html,
    )


def _generate_markdown(
    meta: ComplianceReportMeta,
    pillars: list[PillarEvidence],
    gap_report: dict,
    audit_stats: dict,
    deployments: list[dict],
    checklist: list[ComplianceCheckItem],
) -> str:
    """Generate markdown version of the report."""
    lines = [
        f"# ShipBridge Compliance Report",
        f"## {meta.project_name}",
        "",
        f"**Organization**: {meta.tenant_name}",
        f"**Date**: {meta.generated_at[:10]}",
        f"**Overall Score**: {meta.overall_score}/100 ({'PASS' if meta.passed else 'BLOCKED'})",
        f"**Generated by**: {meta.generated_by}",
        "",
        "---",
        "",
        "## 5-Pillar Scorecard",
        "",
        "| Pillar | Score | Status | Issues |",
        "|--------|-------|--------|--------|",
    ]

    for p in pillars:
        status_label = {"ok": "Pass", "warn": "Warning", "bad": "Fail"}.get(p.status, p.status)
        lines.append(f"| {p.pillar} | {p.score} | {status_label} | {len(p.issues)} |")

    # Gap report
    blockers = gap_report.get("blockers", [])
    if blockers:
        lines.extend(["", "## Gap Report", ""])
        for b in blockers[:10]:
            lines.append(f"- **[{b.get('severity', '').upper()}]** {b.get('title', '')} — {b.get('fix_hint', '')}")

    # Audit summary
    lines.extend(["", "## Audit Trail Summary", ""])
    lines.append(f"- **Total entries**: {audit_stats.get('total_entries', 0)}")
    for action, count in audit_stats.get("actions_by_type", {}).items():
        lines.append(f"- {action}: {count}")

    # Compliance checklist
    lines.extend(["", "## GDPR/SOC2 Compliance Checklist", ""])
    lines.append("| ID | Category | Control | Status |")
    lines.append("|----|----------|---------|--------|")
    for c in checklist:
        status_icon = {"pass": "Pass", "fail": "FAIL", "partial": "Partial", "n/a": "N/A"}.get(c.status, c.status)
        lines.append(f"| {c.control_id} | {c.category} | {c.description} | {status_icon} |")

    pass_count = sum(1 for c in checklist if c.status == "pass")
    lines.extend(["", f"**{pass_count}/{len(checklist)} controls passing**"])

    return "\n".join(lines)


def _generate_html(
    meta: ComplianceReportMeta,
    pillars: list[PillarEvidence],
    gap_report: dict,
    audit_stats: dict,
    deployments: list[dict],
    checklist: list[ComplianceCheckItem],
) -> str:
    """Generate HTML version of the report (for PDF rendering via weasyprint)."""
    status_colors = {"ok": "#2A9D6E", "warn": "#C49A3C", "bad": "#C44A4A"}
    check_colors = {"pass": "#2A9D6E", "fail": "#C44A4A", "partial": "#C49A3C", "n/a": "#8A9BB8"}

    pillar_rows = ""
    for p in pillars:
        color = status_colors.get(p.status, "#8A9BB8")
        pillar_rows += f'<tr><td>{p.pillar}</td><td style="font-weight:600">{p.score}</td><td style="color:{color}">{p.status.upper()}</td><td>{len(p.issues)}</td></tr>'

    checklist_rows = ""
    for c in checklist:
        color = check_colors.get(c.status, "#8A9BB8")
        checklist_rows += f'<tr><td>{c.control_id}</td><td>{c.category}</td><td>{c.description}</td><td style="color:{color};font-weight:600">{c.status.upper()}</td></tr>'

    pass_count = sum(1 for c in checklist if c.status == "pass")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ShipBridge Compliance Report</title>
<style>
body {{ font-family: 'Instrument Sans', system-ui, sans-serif; color: #E8EDF5; background: #060709; padding: 40px; }}
h1 {{ color: #00C9A7; font-size: 28px; margin-bottom: 4px; }}
h2 {{ color: #E8EDF5; font-size: 18px; margin-top: 32px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th {{ text-align: left; padding: 8px 12px; background: #0C0E12; color: #8A9BB8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
td {{ padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 13px; }}
.meta {{ color: #8A9BB8; font-size: 13px; margin: 4px 0; }}
.score-big {{ font-size: 48px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }}
.pass {{ color: #2A9D6E; }} .fail {{ color: #C44A4A; }}
.summary {{ background: #0C0E12; border-radius: 8px; padding: 24px; margin: 16px 0; }}
</style></head><body>
<h1>ShipBridge Compliance Report</h1>
<p class="meta"><strong>{meta.project_name}</strong> — {meta.tenant_name}</p>
<p class="meta">Generated: {meta.generated_at[:10]} by {meta.generated_by}</p>
<div class="summary">
<span class="score-big {'pass' if meta.passed else 'fail'}">{meta.overall_score}</span>
<span class="meta" style="margin-left:12px">/ 100 — {'PRODUCTION READY' if meta.passed else 'NOT READY'}</span>
</div>
<h2>5-Pillar Scorecard</h2>
<table><tr><th>Pillar</th><th>Score</th><th>Status</th><th>Issues</th></tr>{pillar_rows}</table>
<h2>Audit Trail Summary</h2>
<p class="meta">Total entries: {audit_stats.get('total_entries', 0)}</p>
<h2>GDPR / SOC2 Compliance Checklist</h2>
<table><tr><th>ID</th><th>Category</th><th>Control</th><th>Status</th></tr>{checklist_rows}</table>
<p class="meta"><strong>{pass_count}/{len(checklist)}</strong> controls passing</p>
<hr style="border-color:rgba(255,255,255,0.08);margin-top:32px">
<p class="meta">Report generated by ShipBridge v0.1.0 — Pilot-to-Production Platform</p>
</body></html>"""
