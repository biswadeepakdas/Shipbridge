"""Five-pillar scoring framework for AI agent production readiness."""

from pydantic import BaseModel


class Issue(BaseModel):
    """A single blocker or warning found during assessment."""

    title: str
    evidence: str
    fix_hint: str
    severity: str  # "high", "medium", "low"
    effort_days: int


class PillarScore(BaseModel):
    """Score for one assessment pillar."""

    score: int  # 0–100
    status: str  # "ok", "warn", "bad"
    issues: list[Issue]
    note: str


def _status_from_score(score: int) -> str:
    """Derive status label from numeric score."""
    if score >= 75:
        return "ok"
    if score >= 50:
        return "warn"
    return "bad"


class ReliabilityScorer:
    """Scores compound accuracy, retry logic, circuit breaker presence."""

    def score(self, stack_json: dict, framework: str) -> PillarScore:
        """Evaluate reliability signals in project config."""
        score = 50
        issues: list[Issue] = []

        # Check for retry/fallback config
        tools = stack_json.get("tools", [])
        models = stack_json.get("models", [])

        if len(models) > 1:
            score += 15  # Multi-model = fallback capability
        else:
            issues.append(Issue(
                title="Single model dependency",
                evidence=f"Only {models[0] if models else 'unknown'} configured",
                fix_hint="Add a fallback model for resilience",
                severity="medium",
                effort_days=1,
            ))

        # Framework-specific scoring
        if framework in ("langraph", "crewai"):
            score += 10  # Structured frameworks have better reliability primitives

        # Check for deployment config
        deployment = stack_json.get("deployment", "")
        if deployment:
            score += 10
        else:
            issues.append(Issue(
                title="No deployment target configured",
                evidence="Missing deployment field in stack config",
                fix_hint="Set deployment to railway, vercel, or aws",
                severity="high",
                effort_days=1,
            ))

        # Tool integration breadth
        if len(tools) >= 2:
            score += 10
        elif len(tools) == 1:
            score += 5

        score = min(100, max(0, score))
        return PillarScore(
            score=score,
            status=_status_from_score(score),
            issues=issues,
            note=f"Framework: {framework}, {len(models)} model(s), {len(tools)} tool(s)",
        )


class SecurityScorer:
    """Checks MCP endpoint auth, prompt injection surfaces."""

    def score(self, stack_json: dict, framework: str) -> PillarScore:
        """Evaluate security posture from config."""
        score = 40
        issues: list[Issue] = []

        tools = stack_json.get("tools", [])
        models = stack_json.get("models", [])

        # Check for auth configuration
        auth_config = stack_json.get("auth", {})
        if auth_config:
            score += 20
        else:
            issues.append(Issue(
                title="No authentication configured",
                evidence="Missing auth field in stack config",
                fix_hint="Add OAuth2 or API key authentication to all endpoints",
                severity="high",
                effort_days=2,
            ))

        # Prompt injection surface assessment
        has_user_input = stack_json.get("user_input", True)  # assume true by default
        if has_user_input:
            injection_guard = stack_json.get("injection_guard", False)
            if injection_guard:
                score += 20
            else:
                issues.append(Issue(
                    title="No prompt injection guard",
                    evidence="Agent accepts user input without injection filtering",
                    fix_hint="Add input sanitization and prompt injection detection",
                    severity="high",
                    effort_days=2,
                ))

        # MCP endpoint security
        mcp_endpoints = stack_json.get("mcp_endpoints", [])
        if mcp_endpoints:
            mcp_auth = stack_json.get("mcp_auth", False)
            if mcp_auth:
                score += 15
            else:
                issues.append(Issue(
                    title="Unauthenticated MCP endpoints",
                    evidence=f"{len(mcp_endpoints)} MCP endpoint(s) without auth",
                    fix_hint="Add authentication to all MCP tool endpoints",
                    severity="high",
                    effort_days=1,
                ))
        else:
            score += 15  # No MCP endpoints = no MCP risk

        # Secret management
        secrets_managed = stack_json.get("secrets_vault", False)
        if secrets_managed:
            score += 5

        score = min(100, max(0, score))
        return PillarScore(
            score=score,
            status=_status_from_score(score),
            issues=issues,
            note=f"{len(issues)} security issue(s) detected",
        )


class EvalScorer:
    """Detects CI grader presence, test coverage signals."""

    def score(self, stack_json: dict, framework: str) -> PillarScore:
        """Evaluate evaluation/testing readiness."""
        score = 30
        issues: list[Issue] = []

        # CI grader presence
        ci_grader = stack_json.get("ci_grader", False)
        if ci_grader:
            score += 25
        else:
            issues.append(Issue(
                title="No CI grader configured",
                evidence="No automated evaluation in CI pipeline",
                fix_hint="Add LLM-as-judge grader to CI with score threshold gate",
                severity="high",
                effort_days=3,
            ))

        # Test coverage
        test_coverage = stack_json.get("test_coverage", 0)
        if test_coverage >= 80:
            score += 20
        elif test_coverage >= 50:
            score += 10
            issues.append(Issue(
                title="Low test coverage",
                evidence=f"Test coverage at {test_coverage}%",
                fix_hint="Increase test coverage to 80%+ for production readiness",
                severity="medium",
                effort_days=3,
            ))
        else:
            issues.append(Issue(
                title="Insufficient test coverage",
                evidence=f"Test coverage at {test_coverage}%" if test_coverage > 0 else "No test coverage data",
                fix_hint="Add unit and integration tests targeting 80% coverage",
                severity="high",
                effort_days=5,
            ))

        # Baseline capture
        has_baseline = stack_json.get("eval_baseline", False)
        if has_baseline:
            score += 15
        else:
            issues.append(Issue(
                title="No evaluation baseline",
                evidence="No golden baseline captured for regression detection",
                fix_hint="Run agent against seed dataset and store results as baseline",
                severity="medium",
                effort_days=2,
            ))

        # Eval dataset
        has_dataset = stack_json.get("eval_dataset", False)
        if has_dataset:
            score += 10

        score = min(100, max(0, score))
        return PillarScore(
            score=score,
            status=_status_from_score(score),
            issues=issues,
            note=f"CI grader: {'yes' if ci_grader else 'no'}, coverage: {test_coverage}%",
        )


class GovernanceScorer:
    """Checks audit trail, HITL gate configuration, ownership records."""

    def score(self, stack_json: dict, framework: str) -> PillarScore:
        """Evaluate governance and compliance readiness."""
        score = 30
        issues: list[Issue] = []

        # Audit trail
        has_audit = stack_json.get("audit_trail", False)
        if has_audit:
            score += 25
        else:
            issues.append(Issue(
                title="No audit trail configured",
                evidence="Agent actions are not logged to immutable audit log",
                fix_hint="Enable audit logging for all tool calls and LLM decisions",
                severity="high",
                effort_days=2,
            ))

        # HITL gates
        has_hitl = stack_json.get("hitl_gates", False)
        if has_hitl:
            score += 20
        else:
            issues.append(Issue(
                title="No human-in-the-loop gates",
                evidence="No HITL approval required for high-risk actions",
                fix_hint="Configure HITL gates for actions above risk threshold",
                severity="high",
                effort_days=3,
            ))

        # Ownership
        has_owner = stack_json.get("owner", "")
        if has_owner:
            score += 10
        else:
            issues.append(Issue(
                title="No ownership record",
                evidence="No designated owner for this agent system",
                fix_hint="Assign an owner responsible for production operations",
                severity="medium",
                effort_days=0,
            ))

        # Compliance documentation
        has_compliance = stack_json.get("compliance_docs", False)
        if has_compliance:
            score += 15

        score = min(100, max(0, score))
        return PillarScore(
            score=score,
            status=_status_from_score(score),
            issues=issues,
            note=f"Audit: {'yes' if has_audit else 'no'}, HITL: {'yes' if has_hitl else 'no'}",
        )


class CostScorer:
    """Analyses model routing, semantic cache, projects production cost."""

    def score(self, stack_json: dict, framework: str) -> PillarScore:
        """Evaluate cost optimization signals."""
        score = 40
        issues: list[Issue] = []

        models = stack_json.get("models", [])

        # Multi-model routing (tier optimization)
        if len(models) >= 3:
            score += 25  # 3-tier routing
        elif len(models) == 2:
            score += 15  # 2-tier routing
            issues.append(Issue(
                title="Only 2-tier model routing",
                evidence=f"Using {', '.join(models)}",
                fix_hint="Add a third tier (e.g., Haiku) for simple tasks to reduce cost",
                severity="low",
                effort_days=1,
            ))
        else:
            issues.append(Issue(
                title="No model routing configured",
                evidence=f"Single model: {models[0] if models else 'unknown'}",
                fix_hint="Implement 3-tier routing: Haiku for simple, Sonnet for medium, Opus for complex",
                severity="medium",
                effort_days=2,
            ))

        # Semantic cache
        has_cache = stack_json.get("semantic_cache", False)
        if has_cache:
            score += 20
        else:
            issues.append(Issue(
                title="No semantic cache",
                evidence="Repeated queries hit the model every time",
                fix_hint="Add semantic cache with Redis to reduce redundant LLM calls",
                severity="medium",
                effort_days=2,
            ))

        # Token budget enforcement
        has_budget = stack_json.get("token_budget", False)
        if has_budget:
            score += 15
        else:
            issues.append(Issue(
                title="No token budget enforcement",
                evidence="No limit on tokens per request or per hour",
                fix_hint="Set per-request and per-hour token limits to prevent cost spikes",
                severity="medium",
                effort_days=1,
            ))

        score = min(100, max(0, score))
        return PillarScore(
            score=score,
            status=_status_from_score(score),
            issues=issues,
            note=f"{len(models)} model(s), cache: {'yes' if has_cache else 'no'}",
        )
