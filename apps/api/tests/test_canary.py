"""Tests for canary logic — metrics collection, comparison, stage activities, rollback."""

import pytest

from app.workers.canary import (
    CanaryHealth,
    collect_metrics,
    compare_metrics,
    execute_canary5,
    execute_canary25,
    execute_production,
    execute_rollback,
    execute_sandbox,
    run_canary_pipeline,
)


# --- Unit tests: metrics collection ---

class TestMetricsCollector:
    def test_sandbox_metrics(self) -> None:
        m = collect_metrics("sandbox", 0)
        assert m.task_success_rate > 0.90
        assert m.latency_p50_ms > 0
        assert m.latency_p95_ms > m.latency_p50_ms
        assert m.latency_p99_ms > m.latency_p95_ms

    def test_canary5_metrics(self) -> None:
        m = collect_metrics("canary5", 5)
        assert m.requests_per_minute > 0

    def test_regression_worsens_metrics(self) -> None:
        normal = collect_metrics("canary5", 5)
        regressed = collect_metrics("canary5", 5, inject_regression=True)
        assert regressed.task_success_rate < normal.task_success_rate
        assert regressed.error_rate > normal.error_rate
        assert regressed.latency_p95_ms > normal.latency_p95_ms


# --- Unit tests: metric comparison ---

class TestMetricComparison:
    def test_healthy_comparison(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        canary = collect_metrics("canary5", 5)
        comp = compare_metrics(baseline, canary)
        assert comp.health == CanaryHealth.HEALTHY

    def test_regression_detected(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        regressed = collect_metrics("canary5", 5, inject_regression=True)
        comp = compare_metrics(baseline, regressed)
        assert comp.health == CanaryHealth.REGRESSION
        assert "rollback" in comp.recommendation.lower() or "investigate" in comp.recommendation.lower()

    def test_deltas_calculated(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        canary = collect_metrics("canary25", 25)
        comp = compare_metrics(baseline, canary)
        # Canary should have slightly worse metrics
        assert comp.success_rate_delta <= 0
        assert comp.latency_delta_ms >= 0


# --- Unit tests: stage activities ---

class TestStageActivities:
    def test_sandbox_passes_normally(self) -> None:
        result = execute_sandbox()
        assert result.passed is True
        assert result.stage_name == "sandbox"
        assert result.traffic_pct == 0

    def test_sandbox_fails_on_regression(self) -> None:
        result = execute_sandbox(inject_regression=True)
        assert result.passed is False

    def test_canary5_passes_normally(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        result = execute_canary5(baseline)
        assert result.passed is True
        assert result.traffic_pct == 5
        assert result.comparison is not None

    def test_canary5_fails_on_regression(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        result = execute_canary5(baseline, inject_regression=True)
        assert result.passed is False
        assert result.comparison.health == CanaryHealth.REGRESSION

    def test_canary25_passes_normally(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        result = execute_canary25(baseline)
        assert result.passed is True
        assert result.traffic_pct == 25

    def test_production_completes(self) -> None:
        baseline = collect_metrics("sandbox", 0)
        result = execute_production(baseline)
        assert result.passed is True
        assert result.traffic_pct == 100

    def test_rollback_generates_notification(self) -> None:
        result = execute_rollback("canary5", "Success rate dropped 12%")
        assert result["action"] == "rollback"
        assert result["from_stage"] == "canary5"
        assert "notification" in result
        assert "slack" in result["notification"]["channel"]


# --- Unit tests: full canary pipeline ---

class TestCanaryPipeline:
    def test_full_pipeline_succeeds(self) -> None:
        results = run_canary_pipeline()
        assert len(results) == 4
        assert all(r.passed for r in results)
        stages = [r.stage_name for r in results]
        assert stages == ["sandbox", "canary5", "canary25", "production"]

    def test_pipeline_stops_on_sandbox_regression(self) -> None:
        results = run_canary_pipeline(inject_regression_at="sandbox")
        assert len(results) == 1
        assert results[0].passed is False

    def test_pipeline_stops_on_canary5_regression(self) -> None:
        results = run_canary_pipeline(inject_regression_at="canary5")
        assert len(results) == 2
        assert results[0].passed is True  # sandbox ok
        assert results[1].passed is False  # canary5 regressed

    def test_pipeline_stops_on_canary25_regression(self) -> None:
        results = run_canary_pipeline(inject_regression_at="canary25")
        assert len(results) == 3
        assert results[2].passed is False

    def test_each_stage_has_metrics(self) -> None:
        results = run_canary_pipeline()
        for r in results:
            assert r.metrics.task_success_rate > 0
            assert r.metrics.latency_p95_ms > 0

    def test_canary_stages_have_comparisons(self) -> None:
        results = run_canary_pipeline()
        # sandbox has no comparison, canary5/25/prod do
        assert results[0].comparison is None
        assert results[1].comparison is not None
        assert results[2].comparison is not None
        assert results[3].comparison is not None
