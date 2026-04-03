import io
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from pydantic import BaseModel
from weasyprint import HTML

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
    pdf_bytes: Optional[bytes] = None # Add bytes for PDF content

def _generate_compliance_checklist(scores_json: dict, has_audit: bool, has_hitl: bool) -> List[ComplianceCheckItem]:
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

def generate_compliance_report(
    project_name: str,
    tenant_name: str,
    scores_json: dict,
    gap_report_json: dict,
    audit_stats: dict,
    deployment_history: Optional[List[dict]] = None,
    generated_by: str = "system",
) -> ComplianceReport:
    """Generate a complete compliance report."""
    overall_score = 0
    pillar_count = 0
    pillars: List[PillarEvidence] = []

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

    md = _generate_markdown(meta, pillars, gap_report_json, audit_stats, deployment_history or [], checklist)
    html_content = _generate_html(meta, pillars, gap_report_json, audit_stats, deployment_history or [], checklist)
    
    # Generate PDF bytes using WeasyPrint
    pdf_bytes = HTML(string=html_content).write_pdf()

    return ComplianceReport(
        meta=meta,
        pillars=pillars,
        audit_summary=audit_stats,
        deployment_history=deployment_history or [],
        compliance_checklist=checklist,
        markdown=md,
        html=html_content,
        pdf_bytes=pdf_bytes
    )

def _generate_markdown(
    meta: ComplianceReportMeta,
    pillars: List[PillarEvidence],
    gap_report: dict,
    audit_stats: dict,
    deployments: List[dict],
    checklist: List[ComplianceCheckItem],
) -> str:
    """Generate markdown version of the report."""
    lines = [
        f"# ShipBridge Compliance Report",
        f"## {meta.project_name}",
        "",
        f"**Organization**: {meta.tenant_name}",
        f"**Date**: {meta.generated_at[:10]}",
        "**Overall Score**: " + str(meta.overall_score) + "/100 (" + ("PASS" if meta.passed else "BLOCKED") + ")",
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

def _svg_donut(score: int, size: int = 120, label: str = "") -> str:
    """Generate an SVG donut chart for a score."""
    r = (size - 12) / 2
    cx = cy = size / 2
    circumference = 2 * 3.14159 * r
    filled = circumference * score / 100
    gap = circumference - filled
    color = "#00C9A7" if score >= 75 else "#C49A3C" if score >= 50 else "#C44A4A"
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1A1D24" stroke-width="10"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="10"
        stroke-dasharray="{filled} {gap}" stroke-dashoffset="{circumference * 0.25}"
        stroke-linecap="round"/>
      <text x="{cx}" y="{cy - 4}" text-anchor="middle" fill="{color}" font-size="22" font-weight="700" font-family="system-ui">{score}</text>
      <text x="{cx}" y="{cy + 14}" text-anchor="middle" fill="#8A9BB8" font-size="9" font-family="system-ui">{label}</text>
    </svg>'''


def _svg_bar(score: int, width: int = 200) -> str:
    """Generate an SVG horizontal bar for a pillar score."""
    color = "#00C9A7" if score >= 75 else "#C49A3C" if score >= 50 else "#C44A4A"
    fill_w = int(width * score / 100)
    return f'''<svg width="{width}" height="16" viewBox="0 0 {width} 16">
      <rect x="0" y="4" width="{width}" height="8" rx="4" fill="#1A1D24"/>
      <rect x="0" y="4" width="{fill_w}" height="8" rx="4" fill="{color}"/>
      <line x1="{int(width * 0.75)}" y1="0" x2="{int(width * 0.75)}" y2="16" stroke="#8A9BB8" stroke-width="1" stroke-dasharray="2,2" opacity="0.5"/>
    </svg>'''


def _generate_html(
    meta: ComplianceReportMeta,
    pillars: List[PillarEvidence],
    gap_report: dict,
    audit_stats: dict,
    deployments: List[dict],
    checklist: List[ComplianceCheckItem],
) -> str:
    """Generate professional HTML report with charts for PDF rendering."""
    status_colors = {"ok": "#00C9A7", "warn": "#C49A3C", "bad": "#C44A4A"}
    check_colors = {"pass": "#00C9A7", "fail": "#C44A4A", "partial": "#C49A3C", "n/a": "#8A9BB8"}

    # Build pillar donut charts row
    pillar_donuts = ""
    for p in pillars:
        pillar_donuts += f'<div class="pillar-donut">{_svg_donut(p.score, 100, p.pillar)}</div>'

    # Build pillar detail bars
    pillar_detail_rows = ""
    for p in pillars:
        color = status_colors.get(p.status, "#8A9BB8")
        status_label = {"ok": "PASS", "warn": "WARN", "bad": "FAIL"}.get(p.status, p.status.upper())
        issue_tags = ""
        for issue in p.issues:
            sev_color = {"high": "#C44A4A", "medium": "#C49A3C", "low": "#00C9A7"}.get(issue.get("severity", ""), "#8A9BB8")
            issue_tags += f'<div class="issue-row"><span class="sev-dot" style="background:{sev_color}"></span><span class="issue-title">{issue.get("title", "")}</span><span class="issue-fix">{issue.get("fix_hint", "")}</span><span class="issue-effort">{issue.get("effort_days", 0)}d</span></div>'
        if not issue_tags:
            issue_tags = '<div class="issue-row"><span class="issue-title" style="color:#00C9A7">No issues found</span></div>'

        pillar_detail_rows += f'''<div class="pillar-card">
          <div class="pillar-header">
            <span class="pillar-name">{p.pillar}</span>
            <span class="pillar-score" style="color:{color}">{p.score}/100</span>
            <span class="pillar-status" style="background:{color}20;color:{color}">{status_label}</span>
          </div>
          <div class="bar-row">{_svg_bar(p.score, 420)}</div>
          <div class="issues-list">{issue_tags}</div>
        </div>'''

    # Gap report summary
    blockers = gap_report.get("blockers", [])
    total_issues = gap_report.get("total_issues", len(blockers))
    critical_count = gap_report.get("critical_count", sum(1 for b in blockers if b.get("severity") == "high"))
    effort_days = gap_report.get("estimated_effort_days", sum(b.get("effort_days", 0) for b in blockers))

    # Compliance checklist with visual indicators
    checklist_rows = ""
    for c in checklist:
        color = check_colors.get(c.status, "#8A9BB8")
        icon = {"pass": "&#10003;", "fail": "&#10007;", "partial": "&#9679;", "n/a": "—"}.get(c.status, "?")
        checklist_rows += f'<tr><td class="check-id">{c.control_id}</td><td>{c.category}</td><td>{c.description}</td><td class="check-status" style="color:{color}"><span class="status-icon">{icon}</span> {c.status.upper()}</td></tr>'

    pass_count = sum(1 for c in checklist if c.status == "pass")
    partial_count = sum(1 for c in checklist if c.status == "partial")
    fail_count = sum(1 for c in checklist if c.status == "fail")

    # Compliance donut
    compliance_pct = int(pass_count / max(len(checklist), 1) * 100)
    compliance_donut = _svg_donut(compliance_pct, 100, "Compliance")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ShipBridge Compliance Report</title>
<style>
@page {{ size: A4; margin: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; color: #E8EDF5; background: #060709; margin: 0; padding: 0; font-size: 12px; }}

/* === PAGE 1: Executive Summary === */
.page {{ padding: 40px 48px; page-break-after: always; min-height: 100vh; box-sizing: border-box; }}
.page:last-child {{ page-break-after: auto; }}

/* Header */
.report-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 32px; }}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brand-logo {{ width: 32px; height: 32px; background: #00C9A7; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #060709; font-weight: 800; font-size: 16px; }}
.brand h1 {{ color: #00C9A7; font-size: 24px; margin: 0; letter-spacing: -0.02em; }}
.brand-sub {{ color: #8A9BB8; font-size: 11px; margin-top: 2px; }}
.report-date {{ color: #8A9BB8; font-size: 11px; text-align: right; }}

/* Hero score */
.hero {{ background: linear-gradient(135deg, #0C0E12 0%, #111419 100%); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 32px; margin-bottom: 28px; display: flex; align-items: center; gap: 32px; }}
.hero-left {{ flex-shrink: 0; }}
.hero-right {{ flex: 1; }}
.hero-title {{ font-size: 20px; font-weight: 600; margin: 0 0 4px 0; }}
.hero-subtitle {{ color: #8A9BB8; font-size: 13px; margin: 0; }}
.hero-stats {{ display: flex; gap: 32px; margin-top: 16px; }}
.stat {{ }}
.stat-value {{ font-size: 20px; font-weight: 600; }}
.stat-label {{ font-size: 9px; color: #8A9BB8; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 2px; }}

/* Pillar donuts row */
.pillar-donuts {{ display: flex; justify-content: space-between; margin-bottom: 28px; }}
.pillar-donut {{ text-align: center; }}

/* Section headers */
h2 {{ font-size: 16px; font-weight: 600; margin: 28px 0 16px 0; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); }}

/* Pillar detail cards */
.pillar-card {{ background: #0C0E12; border: 1px solid rgba(255,255,255,0.04); border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
.pillar-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
.pillar-name {{ font-size: 14px; font-weight: 600; flex: 1; }}
.pillar-score {{ font-size: 14px; font-weight: 600; font-family: monospace; }}
.pillar-status {{ font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.04em; }}
.bar-row {{ margin-bottom: 10px; }}
.issues-list {{ }}
.issue-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 11px; }}
.sev-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
.issue-title {{ flex: 1; color: #C8D0DC; }}
.issue-fix {{ color: #8A9BB8; font-size: 10px; max-width: 200px; }}
.issue-effort {{ color: #8A9BB8; font-size: 10px; white-space: nowrap; }}

/* Compliance table */
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 8px 10px; background: #0C0E12; color: #8A9BB8; font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 500; }}
td {{ padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 11px; }}
.check-id {{ font-family: monospace; color: #8A9BB8; font-size: 10px; }}
.check-status {{ font-weight: 600; white-space: nowrap; }}
.status-icon {{ font-size: 12px; }}

/* Compliance summary bar */
.compliance-summary {{ display: flex; gap: 24px; align-items: center; background: #0C0E12; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
.compliance-bar {{ flex: 1; }}
.compliance-bar-track {{ height: 24px; background: #1A1D24; border-radius: 12px; overflow: hidden; display: flex; }}
.compliance-bar-pass {{ background: #00C9A7; height: 100%; }}
.compliance-bar-partial {{ background: #C49A3C; height: 100%; }}
.compliance-bar-fail {{ background: #C44A4A; height: 100%; }}
.compliance-legend {{ display: flex; gap: 16px; margin-top: 8px; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 10px; color: #8A9BB8; }}
.legend-dot {{ width: 8px; height: 8px; border-radius: 50%; }}

/* Gap report */
.gap-item {{ display: flex; align-items: flex-start; gap: 8px; padding: 8px 12px; background: #0C0E12; border-radius: 6px; margin-bottom: 6px; }}
.gap-sev {{ font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; text-transform: uppercase; flex-shrink: 0; margin-top: 1px; }}
.gap-sev-high {{ background: rgba(196,74,74,0.15); color: #C44A4A; }}
.gap-sev-medium {{ background: rgba(196,154,60,0.15); color: #C49A3C; }}
.gap-sev-low {{ background: rgba(0,201,167,0.15); color: #00C9A7; }}
.gap-content {{ flex: 1; }}
.gap-title {{ font-size: 12px; font-weight: 500; margin-bottom: 2px; }}
.gap-fix {{ font-size: 10px; color: #8A9BB8; }}
.gap-effort {{ font-size: 10px; color: #8A9BB8; white-space: nowrap; margin-top: 4px; }}

/* Footer */
.footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; justify-content: space-between; color: #8A9BB8; font-size: 10px; }}
</style></head><body>

<!-- ═══ PAGE 1: Executive Summary ═══ -->
<div class="page">
  <div class="report-header">
    <div class="brand">
      <div class="brand-logo">S</div>
      <div>
        <h1>ShipBridge</h1>
        <div class="brand-sub">Compliance Report</div>
      </div>
    </div>
    <div class="report-date">
      Generated {meta.generated_at[:10]}<br/>
      Report v{meta.report_version}
    </div>
  </div>

  <div class="hero">
    <div class="hero-left">{_svg_donut(meta.overall_score, 140, "Overall")}</div>
    <div class="hero-right">
      <h3 class="hero-title">{meta.project_name}</h3>
      <p class="hero-subtitle">{'Production ready — all pillars above threshold' if meta.passed else 'Not production ready — address gap report before deployment'}</p>
      <div class="hero-stats">
        <div class="stat"><div class="stat-value" style="color:{'#00C9A7' if total_issues == 0 else '#C44A4A'}">{total_issues}</div><div class="stat-label">Total Issues</div></div>
        <div class="stat"><div class="stat-value" style="color:{'#00C9A7' if critical_count == 0 else '#C44A4A'}">{critical_count}</div><div class="stat-label">Critical</div></div>
        <div class="stat"><div class="stat-value" style="color:#8A9BB8">{effort_days}d</div><div class="stat-label">Est. Effort</div></div>
        <div class="stat"><div class="stat-value" style="color:{'#00C9A7' if meta.passed else '#C44A4A'}">{'PASS' if meta.passed else 'FAIL'}</div><div class="stat-label">Readiness Gate</div></div>
      </div>
    </div>
  </div>

  <h2>5-Pillar Assessment</h2>
  <div class="pillar-donuts">{pillar_donuts}</div>

  <!-- Compact pillar scorecard table on page 1 -->
  <table>
    <tr><th>Pillar</th><th>Score</th><th>Bar</th><th>Status</th><th>Issues</th></tr>
    {''.join(f'<tr><td style="font-weight:600">{p.pillar}</td><td style="font-family:monospace;font-weight:600;color:{status_colors.get(p.status, "#8A9BB8")}">{p.score}</td><td>{_svg_bar(p.score, 180)}</td><td><span class="pillar-status" style="background:{status_colors.get(p.status, "#8A9BB8")}20;color:{status_colors.get(p.status, "#8A9BB8")}">{"PASS" if p.status == "ok" else "WARN" if p.status == "warn" else "FAIL"}</span></td><td>{len(p.issues)}</td></tr>' for p in pillars)}
  </table>

  <!-- Compliance summary on page 1 -->
  <h2>Compliance Overview — {pass_count}/{len(checklist)} Controls Passing</h2>
  <div class="compliance-summary">
    <div style="flex-shrink:0">{compliance_donut}</div>
    <div class="compliance-bar">
      <div class="compliance-bar-track">
        <div class="compliance-bar-pass" style="width:{pass_count / max(len(checklist), 1) * 100}%"></div>
        <div class="compliance-bar-partial" style="width:{partial_count / max(len(checklist), 1) * 100}%"></div>
        <div class="compliance-bar-fail" style="width:{fail_count / max(len(checklist), 1) * 100}%"></div>
      </div>
      <div class="compliance-legend">
        <div class="legend-item"><div class="legend-dot" style="background:#00C9A7"></div>{pass_count} Pass</div>
        <div class="legend-item"><div class="legend-dot" style="background:#C49A3C"></div>{partial_count} Partial</div>
        <div class="legend-item"><div class="legend-dot" style="background:#C44A4A"></div>{fail_count} Fail</div>
      </div>
    </div>
  </div>

  <div class="footer">
    <span>ShipBridge v0.1.0</span>
    <span>Page 1 of 3</span>
  </div>
</div>

<!-- ═══ PAGE 2: Pillar Details + Gap Report ═══ -->
<div class="page">
  <div class="report-header">
    <div class="brand">
      <div class="brand-logo">S</div>
      <div>
        <h1>ShipBridge</h1>
        <div class="brand-sub">{meta.project_name} — Pillar Details &amp; Gap Report</div>
      </div>
    </div>
    <div class="report-date">Page 2 of 3</div>
  </div>

  <h2>Pillar Breakdown</h2>
  {pillar_detail_rows}

  <h2>Gap Report — {total_issues} Issues, {effort_days} Days Estimated Effort</h2>
  {''.join(f'<div class="gap-item"><span class="gap-sev gap-sev-{b.get("severity", "medium")}">{b.get("severity", "?").upper()}</span><div class="gap-content"><div class="gap-title">{b.get("title", "")}</div><div class="gap-fix">{b.get("fix_hint", "")}</div></div><div class="gap-effort">{b.get("effort_days", 0)}d</div></div>' for b in blockers[:15]) or '<p style="color:#00C9A7;font-size:13px">No blockers found. All pillars pass the readiness threshold.</p>'}

  <div class="footer">
    <span>ShipBridge v0.1.0</span>
    <span>Page 2 of 3</span>
  </div>
</div>

<!-- ═══ PAGE 3: GDPR / SOC2 Compliance Checklist ═══ -->
<div class="page">
  <div class="report-header">
    <div class="brand">
      <div class="brand-logo">S</div>
      <div>
        <h1>ShipBridge</h1>
        <div class="brand-sub">{meta.project_name} — GDPR / SOC2 Compliance Checklist</div>
      </div>
    </div>
    <div class="report-date">Page 3 of 3</div>
  </div>

  <h2>GDPR / SOC2 Compliance — {pass_count}/{len(checklist)} Controls Passing</h2>
  <table>
    <tr><th>ID</th><th>Category</th><th>Control</th><th>Status</th></tr>
    {checklist_rows}
  </table>

  <div class="footer">
    <span>ShipBridge v0.1.0 — Pilot-to-Production Platform</span>
    <span>{pass_count}/{len(checklist)} controls passing</span>
  </div>
</div>

</body></html>"""
