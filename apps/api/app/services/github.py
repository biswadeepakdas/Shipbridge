"""GitHub App integration — webhook handling, PR comments, framework detection."""

import hashlib
import hmac
import re

import structlog

from app.config import get_settings

logger = structlog.get_logger()

# Framework detection patterns — maps file/config patterns to framework names
FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "langraph": ["langgraph", "langraph", "from langgraph"],
    "crewai": ["crewai", "from crewai", "CrewAI"],
    "autogen": ["autogen", "from autogen", "AutoGen"],
    "n8n": ["n8n", "n8n-workflow", "n8n-nodes"],
}

# Files that indicate specific frameworks
FRAMEWORK_FILES: dict[str, str] = {
    "langgraph.json": "langraph",
    "crew.yaml": "crewai",
    "crewai.yaml": "crewai",
    "OAI_CONFIG_LIST": "autogen",
}


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook X-Hub-Signature-256 header."""
    settings = get_settings()
    if not settings.github_webhook_secret:
        logger.warning("github_webhook_secret_not_set")
        return False

    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def detect_framework(file_list: list[str], file_contents: dict[str, str] | None = None) -> str:
    """Auto-detect AI agent framework from repository file list and contents.

    Args:
        file_list: List of file paths in the repository.
        file_contents: Optional dict of {filepath: content} for deeper inspection.

    Returns:
        Detected framework name or "custom" if none detected.
    """
    # Check for framework-specific config files
    for filepath in file_list:
        filename = filepath.split("/")[-1]
        if filename in FRAMEWORK_FILES:
            return FRAMEWORK_FILES[filename]

    # Check package files for framework dependencies
    package_files = {
        "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
        "package.json", "Pipfile",
    }

    if file_contents:
        for filepath, content in file_contents.items():
            filename = filepath.split("/")[-1]

            # Check package dependency files
            if filename in package_files:
                for framework, patterns in FRAMEWORK_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.lower() in content.lower():
                            return framework

            # Check source files for imports
            if filepath.endswith((".py", ".ts", ".js")):
                for framework, patterns in FRAMEWORK_PATTERNS.items():
                    for pattern in patterns:
                        if pattern in content:
                            return framework

    # Check file paths for framework indicators
    for filepath in file_list:
        lower_path = filepath.lower()
        for framework, patterns in FRAMEWORK_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in lower_path:
                    return framework

    return "custom"


def generate_score_badge_svg(score: int, label: str = "readiness") -> str:
    """Generate an SVG badge showing the readiness score.

    Follows shields.io style for GitHub README embedding.
    """
    if score >= 75:
        color = "#2A9D6E"  # ok green
    elif score >= 50:
        color = "#C49A3C"  # warn yellow
    else:
        color = "#C44A4A"  # danger red

    label_width = len(label) * 7 + 10
    value_text = str(score)
    value_width = len(value_text) * 8 + 10
    total_width = label_width + value_width

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {score}">
  <title>{label}: {score}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="{label_width / 2}" y="14">{label}</text>
    <text x="{label_width + value_width / 2}" y="14">{value_text}</text>
  </g>
</svg>"""


def format_pr_comment(
    total_score: int,
    pillars: dict[str, dict],
    gap_report: dict,
    previous_score: int | None = None,
) -> str:
    """Format a structured PR comment with readiness score breakdown."""
    status_emoji = {True: "pass", False: "fail"}
    passed = total_score >= 75

    delta = ""
    if previous_score is not None:
        diff = total_score - previous_score
        delta = f" ({'+' if diff >= 0 else ''}{diff} vs last)"

    lines = [
        f"## ShipBridge Readiness: {'PASS' if passed else 'BLOCKED'} — {total_score}/100{delta}",
        "",
        "| Pillar | Score | Status |",
        "|--------|-------|--------|",
    ]

    for name, pillar in pillars.items():
        score = pillar.get("score", 0)
        status = pillar.get("status", "unknown")
        status_label = {"ok": "Pass", "warn": "Warning", "bad": "Fail"}.get(status, status)
        lines.append(f"| {name.capitalize()} | {score} | {status_label} |")

    lines.append("")

    if gap_report.get("total_issues", 0) > 0:
        critical = gap_report.get("critical_count", 0)
        total = gap_report.get("total_issues", 0)
        effort = gap_report.get("estimated_effort_days", 0)
        lines.append(f"**{total} issues found** ({critical} critical) — est. {effort} days to fix")
        lines.append("")

        blockers = gap_report.get("blockers", [])[:5]
        if blockers:
            lines.append("### Top blockers")
            for b in blockers:
                sev = b.get("severity", "")
                title = b.get("title", "")
                hint = b.get("fix_hint", "")
                lines.append(f"- **[{sev.upper()}]** {title} — {hint}")

    lines.append("")
    lines.append("---")
    lines.append("*Posted by [ShipBridge](https://shipbridge.dev) — Pilot-to-Production Platform*")

    return "\n".join(lines)
