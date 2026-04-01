"""Canary deployment activities — per-stage execution, metrics collection, rollback.

Each activity simulates what Temporal activities would do in production:
- SandboxActivity: run agent in isolated test environment
- Canary5Activity: route 5% traffic, collect 12h metrics
- Canary25Activity: route 25%, compare against sandbox baseline
- MetricsCollector: aggregate task success, latency, cost, escalation
- RollbackActivity: revert to previous stage, notify team
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class CanaryHealth(str, Enum):
    """Canary health assessment."""

    HEALTHY = "healthy"
    REGRESSION = "regression"
    ROLLBACK = "rollback_in_progress"


class MetricSnapshot(BaseModel):
    """Point-in-time metric snapshot during canary monitoring."""

    timestamp: str
    task_success_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    token_cost_per_task: float
    escalation_rate: float
    error_rate: float
    requests_per_minute: float


class CanaryComparison(BaseModel):
    """Comparison of canary metrics against baseline."""

    baseline: MetricSnapshot
    canary: MetricSnapshot
    success_rate_delta: float
    latency_delta_ms: float
    cost_delta: float
    health: CanaryHealth
    recommendation: str


class StageExecutionResult(BaseModel):
    """Result of executing a deployment stage activity."""

    stage_name: str
    traffic_pct: int
    duration_minutes: int
    metrics: MetricSnapshot
    comparison: CanaryComparison | None = None
    passed: bool
    message: str


# --- Metrics Collector ---

def collect_metrics(
    stage_name: str,
    traffic_pct: int,
    inject_regression: bool = False,
) -> MetricSnapshot:
    """Collect metrics for a deployment stage.

    In production: queries Prometheus/Grafana for real service metrics.
    """
    base_configs = {
        "sandbox": {"success": 0.96, "p50": 120, "p95": 250, "p99": 450, "cost": 0.018, "esc": 0.04, "err": 0.04, "rpm": 50},
        "canary5": {"success": 0.94, "p50": 135, "p95": 280, "p99": 500, "cost": 0.021, "esc": 0.05, "err": 0.06, "rpm": 100},
        "canary25": {"success": 0.93, "p50": 140, "p95": 300, "p99": 520, "cost": 0.024, "esc": 0.06, "err": 0.07, "rpm": 500},
        "production": {"success": 0.92, "p50": 145, "p95": 320, "p99": 550, "cost": 0.027, "esc": 0.07, "err": 0.08, "rpm": 2000},
    }

    config = base_configs.get(stage_name, base_configs["sandbox"])

    if inject_regression:
        config["success"] = max(0, config["success"] - 0.12)
        config["err"] = min(1.0, config["err"] + 0.15)
        config["p95"] = config["p95"] * 1.8
        config["p99"] = config["p99"] * 2.0

    return MetricSnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        task_success_rate=config["success"],
        latency_p50_ms=config["p50"],
        latency_p95_ms=config["p95"],
        latency_p99_ms=config["p99"],
        token_cost_per_task=config["cost"],
        escalation_rate=config["esc"],
        error_rate=config["err"],
        requests_per_minute=config["rpm"],
    )


def compare_metrics(baseline: MetricSnapshot, canary: MetricSnapshot) -> CanaryComparison:
    """Compare canary metrics against baseline, determine health."""
    success_delta = canary.task_success_rate - baseline.task_success_rate
    latency_delta = canary.latency_p95_ms - baseline.latency_p95_ms
    cost_delta = canary.token_cost_per_task - baseline.token_cost_per_task

    # Health determination
    if success_delta < -0.05:
        health = CanaryHealth.REGRESSION
        rec = f"Task success dropped {abs(success_delta):.1%} — recommend rollback"
    elif latency_delta > 200:
        health = CanaryHealth.REGRESSION
        rec = f"P95 latency increased by {latency_delta:.0f}ms — investigate"
    else:
        health = CanaryHealth.HEALTHY
        rec = "Metrics within acceptable range — safe to advance"

    return CanaryComparison(
        baseline=baseline,
        canary=canary,
        success_rate_delta=round(success_delta, 4),
        latency_delta_ms=round(latency_delta, 2),
        cost_delta=round(cost_delta, 4),
        health=health,
        recommendation=rec,
    )


# --- Stage Activities ---

def execute_sandbox(inject_regression: bool = False) -> StageExecutionResult:
    """SandboxActivity: run agent in isolated test environment."""
    metrics = collect_metrics("sandbox", 0, inject_regression)
    return StageExecutionResult(
        stage_name="sandbox",
        traffic_pct=0,
        duration_minutes=5,
        metrics=metrics,
        passed=metrics.task_success_rate >= 0.85,
        message="Sandbox execution complete" if metrics.task_success_rate >= 0.85 else "Sandbox failed — success rate too low",
    )


def execute_canary5(baseline: MetricSnapshot, inject_regression: bool = False) -> StageExecutionResult:
    """Canary5Activity: route 5% traffic, collect metrics for 12h minimum."""
    metrics = collect_metrics("canary5", 5, inject_regression)
    comparison = compare_metrics(baseline, metrics)
    passed = comparison.health == CanaryHealth.HEALTHY

    return StageExecutionResult(
        stage_name="canary5",
        traffic_pct=5,
        duration_minutes=720,
        metrics=metrics,
        comparison=comparison,
        passed=passed,
        message=comparison.recommendation,
    )


def execute_canary25(baseline: MetricSnapshot, inject_regression: bool = False) -> StageExecutionResult:
    """Canary25Activity: route 25%, compare against sandbox baseline."""
    metrics = collect_metrics("canary25", 25, inject_regression)
    comparison = compare_metrics(baseline, metrics)
    passed = comparison.health == CanaryHealth.HEALTHY

    return StageExecutionResult(
        stage_name="canary25",
        traffic_pct=25,
        duration_minutes=360,
        metrics=metrics,
        comparison=comparison,
        passed=passed,
        message=comparison.recommendation,
    )


def execute_production(baseline: MetricSnapshot) -> StageExecutionResult:
    """Production rollout at 100% traffic."""
    metrics = collect_metrics("production", 100)
    comparison = compare_metrics(baseline, metrics)

    return StageExecutionResult(
        stage_name="production",
        traffic_pct=100,
        duration_minutes=0,
        metrics=metrics,
        comparison=comparison,
        passed=True,
        message="Production deployment complete",
    )


def execute_rollback(from_stage: str, reason: str) -> dict:
    """RollbackActivity: revert to previous stage, generate notification."""
    logger.warning("rollback_executed", from_stage=from_stage, reason=reason)
    return {
        "action": "rollback",
        "from_stage": from_stage,
        "reason": reason,
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        "notification": {
            "channel": "slack",
            "message": f"Deployment rolled back from {from_stage}: {reason}",
        },
    }


# --- Full Canary Pipeline ---

def run_canary_pipeline(inject_regression_at: str | None = None) -> list[StageExecutionResult]:
    """Execute the full 4-stage canary pipeline. Returns results for each stage."""
    results: list[StageExecutionResult] = []

    # Stage 1: Sandbox
    sandbox = execute_sandbox(inject_regression=inject_regression_at == "sandbox")
    results.append(sandbox)
    if not sandbox.passed:
        return results

    baseline = sandbox.metrics

    # Stage 2: Canary 5%
    canary5 = execute_canary5(baseline, inject_regression=inject_regression_at == "canary5")
    results.append(canary5)
    if not canary5.passed:
        return results

    # Stage 3: Canary 25%
    canary25 = execute_canary25(baseline, inject_regression=inject_regression_at == "canary25")
    results.append(canary25)
    if not canary25.passed:
        return results

    # Stage 4: Production
    prod = execute_production(baseline)
    results.append(prod)
    return results
