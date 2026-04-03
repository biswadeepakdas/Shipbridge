from app.services.chaos_injector import ChaosInjector
from app.config import get_settings
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel
from temporalio import workflow, activity
import structlog
import json

from app.governance.audit import AuditAction, audit_logger

logger = structlog.get_logger()

READINESS_THRESHOLD = 75

class DeployStage(str, Enum):
    SANDBOX = "sandbox"
    CANARY_5 = "canary5"
    CANARY_25 = "canary25"
    PRODUCTION = "production"

class StageStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class StageMetrics(BaseModel):
    task_success_rate: float = 0.0
    latency_p95_ms: float = 0.0
    token_cost_per_task: float = 0.0
    error_rate: float = 0.0

# --- Activities ---

class DeploymentActivities:
    @activity.defn
    async def check_readiness_gate(self, readiness_score: int) -> bool:
        """Verify score >= 75 before advancing."""
        return readiness_score >= READINESS_THRESHOLD

    @activity.defn
    async def collect_real_metrics(self, stage: str, project_id: str) -> StageMetrics:
        """Collect real deployment metrics from Redis counters."""
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            r = aioredis.from_url(settings.redis_url, decode_responses=True)

            # Read metrics from Redis keys set during deployment
            success_key = f"deploy:metrics:{stage}:{project_id}:success"
            fail_key = f"deploy:metrics:{stage}:{project_id}:fail"
            latency_key = f"deploy:metrics:{stage}:{project_id}:latencies"

            success = int(await r.get(success_key) or 0)
            failures = int(await r.get(fail_key) or 0)
            total = success + failures

            success_rate = success / total if total > 0 else 0.0
            error_rate = failures / total if total > 0 else 0.0

            # Get p95 latency from list of recorded latency values
            latencies = await r.lrange(latency_key, 0, -1)
            if latencies:
                lat_values = sorted([float(v) for v in latencies])
                p95_idx = int(len(lat_values) * 0.95)
                p95_latency = lat_values[min(p95_idx, len(lat_values) - 1)]
            else:
                p95_latency = 0.0

            await r.aclose()

            logger.info(
                "metrics_collected",
                stage=stage,
                project_id=project_id,
                success_rate=success_rate,
                p95_latency=p95_latency,
                total=total,
            )

            # If no data yet, return zeros indicating no traffic
            if total == 0:
                return StageMetrics(
                    task_success_rate=0.0,
                    latency_p95_ms=0.0,
                    token_cost_per_task=0.0,
                    error_rate=0.0,
                )

            return StageMetrics(
                task_success_rate=round(success_rate, 4),
                latency_p95_ms=round(p95_latency, 1),
                token_cost_per_task=0.0,  # Computed by cost modeler separately
                error_rate=round(error_rate, 4),
            )
        except Exception as e:
            logger.warning("metrics_collection_failed", stage=stage, project_id=project_id, error=str(e))
            # Return zero metrics on failure — do not block deployment
            return StageMetrics(
                task_success_rate=0.0,
                latency_p95_ms=0.0,
                token_cost_per_task=0.0,
                error_rate=0.0,
            )

    @activity.defn
    async def update_traffic_pct(self, stage: str, project_id: str, pct: int):
        """Update traffic routing in the Integration OS / Gateway."""
        logger.info("traffic_updated", stage=stage, project_id=project_id, pct=pct)

# --- Workflow ---

@workflow.defn
class StagedDeploymentWorkflow:
    @workflow.run
    async def run(self, project_id: str, tenant_id: str, readiness_score: int) -> str:
        # Import WebSocket manager inside workflow to avoid circular dependencies
        try:
            from app.routers.websocket import manager
        except ImportError:
            manager = None
            logger.warning("websocket_manager_not_available", message="WebSocket manager not imported, cannot broadcast deployment updates.")

        async def broadcast_status(stage: DeployStage, status: StageStatus, message: str = ""):
            if manager:
                await manager.broadcast(json.dumps({
                    "type": "deployment_update",
                    "project_id": str(project_id),
                    "stage": stage.value,
                    "status": status.value,
                    "message": message
                }))

        await broadcast_status(DeployStage.SANDBOX, StageStatus.PENDING, "Starting deployment workflow.")

        # 1. Readiness Gate
        passed = await workflow.execute_activity(
            DeploymentActivities.check_readiness_gate,
            readiness_score,
            start_to_close_timeout=timedelta(seconds=10)
        )
        if not passed:
            await broadcast_status(DeployStage.SANDBOX, StageStatus.FAILED, "Readiness gate failed.")
            return "failed_readiness_gate"

        stages = [
            (DeployStage.SANDBOX, 0, timedelta(minutes=5)),
            (DeployStage.CANARY_5, 5, timedelta(hours=12)),
            (DeployStage.CANARY_25, 25, timedelta(hours=6)),
            (DeployStage.PRODUCTION, 100, timedelta(seconds=0))
        ]

        baseline_metrics: Optional[StageMetrics] = None

        for stage_name, traffic_pct, duration in stages:
            await broadcast_status(stage_name, StageStatus.ACTIVE, f"Entering {stage_name.value} stage.")

            # Update Traffic
            await workflow.execute_activity(
                DeploymentActivities.update_traffic_pct,
                args=[stage_name.value, project_id, traffic_pct],
                start_to_close_timeout=timedelta(seconds=30)
            )

            if duration.total_seconds() > 0:
                # Wait for stage duration
                await workflow.sleep(duration)

                # Collect Metrics
                metrics = await workflow.execute_activity(
                    DeploymentActivities.collect_real_metrics,
                    args=[stage_name.value, project_id],
                    start_to_close_timeout=timedelta(seconds=60)
                )

                # Auto-Rollback Check
                if baseline_metrics and (baseline_metrics.task_success_rate - metrics.task_success_rate > 0.05):
                    await workflow.execute_activity(
                        DeploymentActivities.update_traffic_pct,
                        args=["rollback", project_id, 0],
                        start_to_close_timeout=timedelta(seconds=30)
                    )
                    await broadcast_status(stage_name, StageStatus.ROLLED_BACK, f"Rolled back from {stage_name.value} due to metrics degradation.")
                    return f"rolled_back_from_{stage_name.value}"
                
                if stage_name == DeployStage.SANDBOX:
                    baseline_metrics = metrics
            
            await broadcast_status(stage_name, StageStatus.COMPLETE, f"Completed {stage_name.value} stage.")

        await broadcast_status(DeployStage.PRODUCTION, StageStatus.COMPLETE, "Deployment completed successfully.")
        return "completed_successfully"


# ---------------------------------------------------------------------------
# In-process deployment engine (dev / test — no Temporal required)
# ---------------------------------------------------------------------------

def check_readiness_gate(score: int) -> tuple[bool, str]:
    """Check if readiness score meets the deployment threshold."""
    if score >= READINESS_THRESHOLD:
        return True, f"Score {score} meets threshold {READINESS_THRESHOLD}"
    return False, f"Score {score} is below threshold {READINESS_THRESHOLD}"


def simulate_stage_metrics(
    stage: DeployStage,
    inject_regression: bool = False,
) -> StageMetrics:
    """Return simulated metrics for a deployment stage."""
    configs = {
        DeployStage.SANDBOX:    {"sr": 0.96, "lat": 250, "cost": 0.018, "err": 0.04},
        DeployStage.CANARY_5:   {"sr": 0.94, "lat": 280, "cost": 0.021, "err": 0.06},
        DeployStage.CANARY_25:  {"sr": 0.93, "lat": 300, "cost": 0.024, "err": 0.07},
        DeployStage.PRODUCTION: {"sr": 0.92, "lat": 320, "cost": 0.027, "err": 0.08},
    }
    c = dict(configs.get(stage, configs[DeployStage.SANDBOX]))
    if inject_regression:
        c["sr"] = max(0, c["sr"] - 0.12)
        c["err"] = min(1.0, c["err"] + 0.15)
        c["lat"] = c["lat"] * 1.8
    return StageMetrics(
        task_success_rate=c["sr"],
        latency_p95_ms=c["lat"],
        token_cost_per_task=c["cost"],
        error_rate=c["err"],
    )


def check_auto_rollback(
    baseline: StageMetrics | None,
    current: StageMetrics,
) -> tuple[bool, str]:
    """Determine if current metrics warrant an automatic rollback."""
    if baseline is None:
        return False, "No baseline — cannot compare"
    delta = baseline.task_success_rate - current.task_success_rate
    if delta > 0.05:
        return True, f"Success rate dropped by {delta:.1%}"
    return False, "Metrics within acceptable range"


class WorkflowStage(BaseModel):
    name: DeployStage
    status: StageStatus = StageStatus.PENDING
    metrics: StageMetrics | None = None


class WorkflowState(BaseModel):
    id: str
    project_id: str
    tenant_id: str
    status: str  # running | complete | failed | rolled_back
    current_stage: DeployStage | None = None
    stages: list[WorkflowStage] = []
    baseline_metrics: StageMetrics | None = None


class DeploymentEngine:
    """Synchronous in-process deployment engine for dev/test."""

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowState] = {}

    def clear(self) -> None:
        self._workflows.clear()

    def create_workflow(
        self, project_id: str, tenant_id: str, readiness_score: int,
    ) -> WorkflowState:
        passed, msg = check_readiness_gate(readiness_score)
        wf_id = f"deploy-{project_id}-{uuid.uuid4().hex[:8]}"
        stages = [
            WorkflowStage(name=s)
            for s in [DeployStage.SANDBOX, DeployStage.CANARY_5, DeployStage.CANARY_25, DeployStage.PRODUCTION]
        ]
        if not passed:
            wf = WorkflowState(
                id=wf_id, project_id=project_id, tenant_id=tenant_id,
                status="failed", current_stage=None, stages=stages,
            )
        else:
            stages[0].status = StageStatus.ACTIVE
            wf = WorkflowState(
                id=wf_id, project_id=project_id, tenant_id=tenant_id,
                status="running", current_stage=DeployStage.SANDBOX, stages=stages,
            )
        self._workflows[wf_id] = wf
        audit_logger.log(
            tenant_id=tenant_id, action=AuditAction.DEPLOYMENT_EVENT,
            resource_type="deployment", resource_id=wf_id,
            details={"workflow_started": True, "readiness_score": readiness_score},
        )
        return wf

    def get_workflow(self, wf_id: str) -> WorkflowState | None:
        return self._workflows.get(wf_id)

    def list_workflows(self, tenant_id: str) -> list[WorkflowState]:
        return [w for w in self._workflows.values() if w.tenant_id == tenant_id]

    def advance_stage(
        self, wf_id: str, inject_regression: bool = False,
    ) -> WorkflowState:
        wf = self._workflows[wf_id]
        if wf.status != "running" or wf.current_stage is None:
            return wf

        stage_order = [DeployStage.SANDBOX, DeployStage.CANARY_5, DeployStage.CANARY_25, DeployStage.PRODUCTION]
        idx = stage_order.index(wf.current_stage)

        # Collect metrics for current stage
        metrics = simulate_stage_metrics(wf.current_stage, inject_regression)
        wf.stages[idx].metrics = metrics

        # Auto-rollback check
        if wf.baseline_metrics is not None:
            should_rollback, reason = check_auto_rollback(wf.baseline_metrics, metrics)
            if should_rollback:
                wf.stages[idx].status = StageStatus.ROLLED_BACK
                wf.status = "rolled_back"
                return wf

        # Capture baseline from sandbox
        if wf.current_stage == DeployStage.SANDBOX:
            wf.baseline_metrics = metrics

        # Mark complete and advance
        wf.stages[idx].status = StageStatus.COMPLETE

        if idx + 1 < len(stage_order):
            next_stage = stage_order[idx + 1]
            wf.current_stage = next_stage
            wf.stages[idx + 1].status = StageStatus.ACTIVE
        else:
            wf.status = "complete"
            wf.current_stage = None

        return wf


# Singleton for dev/test
deployment_engine = DeploymentEngine()
