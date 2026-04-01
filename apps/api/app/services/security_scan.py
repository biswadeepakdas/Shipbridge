"""Security scan service — prompt injection detection, input sanitization, payload validation."""

import re
from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class SecurityFinding(BaseModel):
    """A single security finding from a scan."""

    category: str
    severity: str  # "critical", "high", "medium", "low"
    title: str
    description: str
    remediation: str


class SecurityScanResult(BaseModel):
    """Result of a security scan."""

    passed: bool
    findings: list[SecurityFinding]
    critical_count: int
    high_count: int
    scanned_fields: int


# Prompt injection patterns
INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?previous\s+instructions", "Instruction override attempt"),
    (r"you\s+are\s+now\s+", "Role reassignment attempt"),
    (r"system\s*prompt", "System prompt extraction attempt"),
    (r"ignore\s+the\s+above", "Context ignore attempt"),
    (r"pretend\s+you\s+are", "Identity manipulation"),
    (r"do\s+not\s+follow", "Instruction bypass"),
    (r"reveal\s+(your|the)\s+(system|initial)", "System prompt reveal attempt"),
    (r"<\s*script", "XSS injection attempt"),
    (r"javascript:", "JavaScript injection"),
    (r"on(error|load|click)\s*=", "Event handler injection"),
]

# SQL injection patterns
SQL_PATTERNS = [
    (r"'\s*or\s+1\s*=\s*1", "SQL OR injection"),
    (r";\s*drop\s+table", "SQL DROP TABLE"),
    (r"union\s+select", "SQL UNION SELECT"),
    (r"--\s*$", "SQL comment injection"),
]

MAX_PAYLOAD_SIZE = 1_048_576  # 1MB


def scan_for_injection(text: str) -> list[SecurityFinding]:
    """Scan text for prompt injection patterns."""
    findings: list[SecurityFinding] = []
    lower = text.lower()

    for pattern, description in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            findings.append(SecurityFinding(
                category="prompt_injection",
                severity="high",
                title=description,
                description=f"Detected pattern: {pattern}",
                remediation="Sanitize user input before passing to LLM",
            ))

    for pattern, description in SQL_PATTERNS:
        if re.search(pattern, lower):
            findings.append(SecurityFinding(
                category="sql_injection",
                severity="critical",
                title=description,
                description=f"Detected SQL injection pattern: {pattern}",
                remediation="Use parameterized queries via ORM",
            ))

    return findings


def scan_payload(payload: dict, max_size: int = MAX_PAYLOAD_SIZE) -> SecurityScanResult:
    """Scan a request payload for security issues."""
    findings: list[SecurityFinding] = []
    scanned = 0

    # Check payload size
    import json
    payload_str = json.dumps(payload)
    if len(payload_str) > max_size:
        findings.append(SecurityFinding(
            category="payload_size",
            severity="medium",
            title="Payload exceeds size limit",
            description=f"Payload is {len(payload_str)} bytes (limit: {max_size})",
            remediation=f"Reduce payload size to under {max_size // 1024}KB",
        ))

    # Scan all string values
    def _scan_values(obj: object, path: str = "") -> None:
        nonlocal scanned
        if isinstance(obj, str):
            scanned += 1
            field_findings = scan_for_injection(obj)
            for f in field_findings:
                f.description = f"{f.description} (field: {path})"
            findings.extend(field_findings)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _scan_values(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan_values(v, f"{path}[{i}]")

    _scan_values(payload)

    critical = sum(1 for f in findings if f.severity == "critical")
    high = sum(1 for f in findings if f.severity == "high")

    return SecurityScanResult(
        passed=critical == 0 and high == 0,
        findings=findings,
        critical_count=critical,
        high_count=high,
        scanned_fields=scanned,
    )


def validate_webhook_payload_size(payload_bytes: bytes, max_size: int = MAX_PAYLOAD_SIZE) -> bool:
    """Reject webhook payloads exceeding size limit."""
    return len(payload_bytes) <= max_size
