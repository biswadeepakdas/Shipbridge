"""Five-pillar scoring framework for AI agent production readiness.

Each scorer accepts static metadata (stack_json) AND optional runtime evidence.
When evidence is provided, scores are based on real signals. When absent, scores
fall back to metadata-only analysis.
"""

from __future__ import annotations

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
    if score >= 75:
        return "ok"
    if score >= 50:
        return "warn"
    return "bad"


def _clamp(val: int) -> int:
    return max(0, min(100, val))


# ---------------------------------------------------------------------------
# Reliability Scorer
# ---------------------------------------------------------------------------


class ReliabilityScorer:
    """Scores reliability from runtime traces, fallback config, and eval results."""

    def score(self, stack_json: dict, framework: str, evidence: dict | None = None) -> PillarScore:
        score = 30
        issues: list[Issue] = []
        ev = evidence or {}
        traces = ev.get("traces", {})
        eval_runs = ev.get("eval_runs", [])
        connector_health = ev.get("connector_health", [])

        # --- Runtime trace signals (highest weight) ---
        if traces.get("total", 0) > 0:
            success_rate = traces.get("success_rate", 0)
            p95_latency = traces.get("p95_latency_ms", 0)
            error_rate = traces.get("error_rate", 0)
            tool_failure_rate = traces.get("tool_failure_rate", 0)

            # Success rate scoring (0-25 pts)
            if success_rate >= 0.98:
                score += 25
            elif success_rate >= 0.95:
                score += 20
            elif success_rate >= 0.90:
                score += 15
                issues.append(Issue(
                    title="Success rate below 95%",
                    evidence=f"Runtime success rate: {success_rate:.1%}",
                    fix_hint="Investigate failing traces and add retry/fallback logic",
                    severity="medium", effort_days=2,
                ))
            else:
                score += 5
                issues.append(Issue(
                    title="Low success rate",
                    evidence=f"Runtime success rate: {success_rate:.1%}",
                    fix_hint="Critical: agent fails too often. Review error traces and fix root causes",
                    severity="high", effort_days=3,
                ))

            # Latency scoring (0-15 pts)
            if p95_latency > 0:
                if p95_latency < 1000:
                    score += 15
                elif p95_latency < 3000:
                    score += 10
                elif p95_latency < 5000:
                    score += 5
                    issues.append(Issue(
                        title="High P95 latency",
                        evidence=f"P95 latency: {p95_latency:.0f}ms",
                        fix_hint="Optimize slow operations or add caching",
                        severity="medium", effort_days=2,
                    ))
                else:
                    issues.append(Issue(
                        title="Very high P95 latency",
                        evidence=f"P95 latency: {p95_latency:.0f}ms",
                        fix_hint="Agent is too slow for production. Profile and optimize",
                        severity="high", effort_days=3,
                    ))

            # Tool failure rate (0-10 pts)
            if tool_failure_rate < 0.05:
                score += 10
            elif tool_failure_rate < 0.10:
                score += 5
                issues.append(Issue(
                    title="Tool call failures",
                    evidence=f"Tool failure rate: {tool_failure_rate:.1%}",
                    fix_hint="Add error handling and retries for external tool calls",
                    severity="medium", effort_days=1,
                ))
            else:
                issues.append(Issue(
                    title="High tool failure rate",
                    evidence=f"Tool failure rate: {tool_failure_rate:.1%}",
                    fix_hint="External tool integrations are unreliable. Add circuit breakers",
                    severity="high", effort_days=2,
                ))
        else:
            # No runtime traces — fall back to static metadata analysis
            models = stack_json.get("models", [])
            tools = stack_json.get("tools", [])

            if len(models) > 1:
                score += 15
            else:
                issues.append(Issue(
                    title="Single model dependency",
                    evidence=f"Only {models[0] if models else 'unknown'} configured",
                    fix_hint="Add a fallback model for resilience",
                    severity="medium", effort_days=1,
                ))

            if framework in ("langraph", "crewai"):
                score += 10

            deployment = stack_json.get("deployment", "")
            if deployment:
                score += 10
            else:
                issues.append(Issue(
                    title="No deployment target configured",
                    evidence="Missing deployment field in stack config",
                    fix_hint="Set deployment to railway, vercel, or aws",
                    severity="high", effort_days=1,
                ))

            if len(tools) >= 2:
                score += 10
            elif len(tools) == 1:
                score += 5

            issues.append(Issue(
                title="No runtime traces",
                evidence="No runtime data available — scoring based on config only",
                fix_hint="Install the ShipBridge SDK or connect an OTel exporter to collect runtime traces",
                severity="medium", effort_days=1,
            ))

        # --- Eval pass rate bonus ---
        if eval_runs:
            latest = eval_runs[0]
            pass_rate = latest.get("pass_rate", 0)
            if pass_rate >= 90:
                score += 10
            elif pass_rate >= 75:
                score += 5

        # --- Connector health ---
        if connector_health:
            healthy = sum(1 for c in connector_health if c.get("status") == "healthy")
            total_c = len(connector_health)
            if total_c > 0 and healthy / total_c < 0.8:
                issues.append(Issue(
                    title="Unhealthy connectors",
                    evidence=f"{total_c - healthy}/{total_c} connectors degraded or down",
                    fix_hint="Check connector configuration and external service health",
                    severity="medium", effort_days=1,
                ))

        note_parts = [f"Framework: {framework}"]
        if traces.get("total", 0) > 0:
            note_parts.append(f"{traces['total']} traces analyzed")
        else:
            note_parts.append("config-only scoring")

        return PillarScore(
            score=_clamp(score),
            status=_status_from_score(_clamp(score)),
            issues=issues,
            note=", ".join(note_parts),
        )


# ---------------------------------------------------------------------------
# Security Scorer
# ---------------------------------------------------------------------------


class SecurityScorer:
    """Checks auth config, prompt injection surfaces, MCP security."""

    def score(self, stack_json: dict, framework: str, evidence: dict | None = None) -> PillarScore:
        score = 40
        issues: list[Issue] = []
        ev = evidence or {}
        ingestion_sources = ev.get("ingestion_sources", [])
        manifest = ev.get("manifest")

        # Auth configuration (from stack or ingestion)
        auth_config = stack_json.get("auth", {})
        has_runtime_auth = any(
            s.get("config_json", {}).get("auth_header")
            for s in ingestion_sources
            if s.get("mode") == "runtime_endpoint"
        )
        if auth_config or has_runtime_auth:
            score += 20
        else:
            issues.append(Issue(
                title="No authentication configured",
                evidence="Missing auth field in stack config",
                fix_hint="Add OAuth2 or API key authentication to all endpoints",
                severity="high", effort_days=2,
            ))

        # Prompt injection guard
        has_user_input = stack_json.get("user_input", True)
        if has_user_input:
            injection_guard = stack_json.get("injection_guard", False)
            # Also check manifest policies
            if manifest and manifest.get("policies", {}).get("injection_guard"):
                injection_guard = True
            if injection_guard:
                score += 20
            else:
                issues.append(Issue(
                    title="No prompt injection guard",
                    evidence="Agent accepts user input without injection filtering",
                    fix_hint="Add input sanitization and prompt injection detection",
                    severity="high", effort_days=2,
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
                    severity="high", effort_days=1,
                ))
        else:
            score += 15

        # Secret management
        secrets_managed = stack_json.get("secrets_vault", False)
        if secrets_managed:
            score += 5

        return PillarScore(
            score=_clamp(score),
            status=_status_from_score(_clamp(score)),
            issues=issues,
            note=f"{len(issues)} security issue(s) detected",
        )


# ---------------------------------------------------------------------------
# Eval Scorer
# ---------------------------------------------------------------------------


class EvalScorer:
    """Detects CI grader presence, test coverage, eval run results."""

    def score(self, stack_json: dict, framework: str, evidence: dict | None = None) -> PillarScore:
        score = 30
        issues: list[Issue] = []
        ev = evidence or {}
        eval_runs = ev.get("eval_runs", [])
        traces = ev.get("traces", {})

        # Real eval run data (highest priority)
        if eval_runs:
            latest = eval_runs[0]
            real_pass_rate = latest.get("pass_rate", 0)
            dataset_size = latest.get("dataset_size", 0)

            # Pass rate scoring
            if real_pass_rate >= 90:
                score += 30
            elif real_pass_rate >= 75:
                score += 20
                issues.append(Issue(
                    title="Eval pass rate below 90%",
                    evidence=f"Latest eval pass rate: {real_pass_rate}%",
                    fix_hint="Review failing eval cases and improve agent responses",
                    severity="medium", effort_days=2,
                ))
            elif real_pass_rate >= 50:
                score += 10
                issues.append(Issue(
                    title="Low eval pass rate",
                    evidence=f"Latest eval pass rate: {real_pass_rate}%",
                    fix_hint="Agent fails too many eval cases. Significant improvements needed",
                    severity="high", effort_days=4,
                ))
            else:
                issues.append(Issue(
                    title="Critical eval failure",
                    evidence=f"Latest eval pass rate: {real_pass_rate}%",
                    fix_hint="Agent cannot pass most eval cases. Review model, prompts, and tools",
                    severity="high", effort_days=5,
                ))

            # Dataset size scoring
            if dataset_size >= 50:
                score += 15
            elif dataset_size >= 20:
                score += 10
            elif dataset_size > 0:
                score += 5
                issues.append(Issue(
                    title="Small eval dataset",
                    evidence=f"Only {dataset_size} eval cases",
                    fix_hint="Add more eval cases for better coverage (target 50+)",
                    severity="low", effort_days=2,
                ))
        else:
            # Fall back to static config
            ci_grader = stack_json.get("ci_grader", False)
            if ci_grader:
                score += 25
            else:
                issues.append(Issue(
                    title="No CI grader configured",
                    evidence="No automated evaluation in CI pipeline",
                    fix_hint="Add LLM-as-judge grader to CI with score threshold gate",
                    severity="high", effort_days=3,
                ))

            test_coverage = stack_json.get("test_coverage", 0)
            if test_coverage >= 80:
                score += 20
            elif test_coverage >= 50:
                score += 10
                issues.append(Issue(
                    title="Low test coverage",
                    evidence=f"Test coverage at {test_coverage}%",
                    fix_hint="Increase test coverage to 80%+ for production readiness",
                    severity="medium", effort_days=3,
                ))
            else:
                issues.append(Issue(
                    title="Insufficient test coverage",
                    evidence=f"Test coverage at {test_coverage}%" if test_coverage > 0 else "No test coverage data",
                    fix_hint="Add unit and integration tests targeting 80% coverage",
                    severity="high", effort_days=5,
                ))

        # Baseline capture
        has_baseline = stack_json.get("eval_baseline", False) or (eval_runs and len(eval_runs) >= 2)
        if has_baseline:
            score += 15
        else:
            issues.append(Issue(
                title="No evaluation baseline",
                evidence="No golden baseline captured for regression detection",
                fix_hint="Run agent against seed dataset and store results as baseline",
                severity="medium", effort_days=2,
            ))

        # Eval dataset presence
        has_dataset = stack_json.get("eval_dataset", False) or bool(eval_runs)
        if has_dataset:
            score += 10

        ci_grader = stack_json.get("ci_grader", False)
        test_coverage = stack_json.get("test_coverage", 0)
        note = f"CI grader: {'yes' if ci_grader else 'no'}, coverage: {test_coverage}%"
        if eval_runs:
            note = f"Eval runs: {len(eval_runs)}, latest pass rate: {eval_runs[0].get('pass_rate', 'N/A')}%"

        return PillarScore(
            score=_clamp(score),
            status=_status_from_score(_clamp(score)),
            issues=issues,
            note=note,
        )


# ---------------------------------------------------------------------------
# Governance Scorer
# ---------------------------------------------------------------------------


class GovernanceScorer:
    """Checks audit trail, HITL gate configuration, ownership records."""

    def score(self, stack_json: dict, framework: str, evidence: dict | None = None) -> PillarScore:
        score = 30
        issues: list[Issue] = []
        ev = evidence or {}
        audit_stats = ev.get("audit_stats", {})
        deployment_history = ev.get("deployment_history", [])

        # Audit trail (from real audit log or config)
        has_real_audit = audit_stats.get("total_entries", 0) > 0
        has_config_audit = stack_json.get("audit_trail", False)
        if has_real_audit:
            score += 25
        elif has_config_audit:
            score += 20
        else:
            issues.append(Issue(
                title="No audit trail configured",
                evidence="Agent actions are not logged to immutable audit log",
                fix_hint="Enable audit logging for all tool calls and LLM decisions",
                severity="high", effort_days=2,
            ))

        # HITL gates
        hitl_gate_count = ev.get("hitl_gate_count", 0)
        has_hitl = hitl_gate_count > 0 or stack_json.get("hitl_gates", False)
        if has_hitl:
            score += 20
        else:
            issues.append(Issue(
                title="No human-in-the-loop gates",
                evidence="No HITL approval required for high-risk actions",
                fix_hint="Configure HITL gates for actions above risk threshold",
                severity="high", effort_days=3,
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
                severity="medium", effort_days=0,
            ))

        # Compliance documentation
        has_compliance = stack_json.get("compliance_docs", False)
        if has_compliance:
            score += 15

        # Deployment history bonus (governance maturity signal)
        if deployment_history:
            completed_deploys = sum(1 for d in deployment_history if d.get("status") == "completed")
            if completed_deploys > 0:
                score += 5

        audit_active = "yes" if has_real_audit else ("config" if has_config_audit else "no")
        return PillarScore(
            score=_clamp(score),
            status=_status_from_score(_clamp(score)),
            issues=issues,
            note=f"Audit: {audit_active}, HITL: {'yes' if has_hitl else 'no'}",
        )


# ---------------------------------------------------------------------------
# Cost Scorer
# ---------------------------------------------------------------------------


class CostScorer:
    """Analyses model routing, token usage, semantic cache, cost projections."""

    def score(self, stack_json: dict, framework: str, evidence: dict | None = None) -> PillarScore:
        score = 40
        issues: list[Issue] = []
        ev = evidence or {}
        traces = ev.get("traces", {})

        models = stack_json.get("models", [])

        # Model routing
        if len(models) >= 3:
            score += 25
        elif len(models) == 2:
            score += 15
            issues.append(Issue(
                title="Only 2-tier model routing",
                evidence=f"Using {', '.join(models)}",
                fix_hint="Add a third tier (e.g., Haiku) for simple tasks to reduce cost",
                severity="low", effort_days=1,
            ))
        else:
            issues.append(Issue(
                title="No model routing configured",
                evidence=f"Single model: {models[0] if models else 'unknown'}",
                fix_hint="Implement 3-tier routing: Haiku for simple, Sonnet for medium, Opus for complex",
                severity="medium", effort_days=2,
            ))

        # Token usage analysis from traces
        if traces.get("total_input_tokens", 0) > 0:
            total_tokens = traces.get("total_input_tokens", 0) + traces.get("total_output_tokens", 0)
            total_traces = traces.get("total", 1)
            avg_tokens_per_call = total_tokens / total_traces
            if avg_tokens_per_call < 2000:
                score += 10
            elif avg_tokens_per_call > 10000:
                issues.append(Issue(
                    title="High token usage per call",
                    evidence=f"Average {avg_tokens_per_call:.0f} tokens/call across {total_traces} traces",
                    fix_hint="Optimize prompts, add summarization, or use smaller context windows",
                    severity="medium", effort_days=2,
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
                severity="medium", effort_days=2,
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
                severity="medium", effort_days=1,
            ))

        cache_str = "yes" if has_cache else "no"
        return PillarScore(
            score=_clamp(score),
            status=_status_from_score(_clamp(score)),
            issues=issues,
            note=f"{len(models)} model(s), cache: {cache_str}",
        )
