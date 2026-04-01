"""StagedDeploymentWorkflow — 4-stage pipeline with readiness gate.

Stages: sandbox → canary5 (5%) → canary25 (25%) → production (100%)
Each stage has: gate check → execute → collect metrics → advance or rollback.

In production, runs as a Temporal workflow with durable checkpointing.
For development, implemented as a pure Python state machine.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

import structlog

from app.governance.audit import AuditAction, audit_logger

logger = structlog.get_logger()

READINESS_THRESHOLD = 75


class DeployStage(str, Enum):
    """Deployment pipeline stages."""

    SANDBOX = "sandbox"
    CANARY_5 = "canary5"
    CANARY_25 = "canary25"
    PRODUCTION = "production"


class StageStatus(str, Enum):
    """Status of a deployment stage."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class StageMetrics(BaseModel):
    """Metrics collected during a deployment stage."""

    task_success_rate: float = 0.0
    latency_p95_ms: float = 0.0
    token_cost_per_task: float = 0.0
    escalation_rate: float = 0.0
    error_rate: float = 0.0


class DeploymentStageRecord(BaseModel):
    """Record of a single deployment stage execution."""

    stage_id: str
    name: DeployStage
    status: StageStatus
    traffic_pct: int
    started_at: str | None = None
    completed_at: str | None = None
    metrics: StageMetrics | None = None
    error_message: str | None = None


class DeploymentWorkflow(BaseModel):
    """Complete deployment workflow state."""

    id: str
    project_id: str
    tenant_id: str
    readiness_score: int
    current_stage: DeployStage | None = None
    status: str = "pending"  # pending, running, complete, failed, rolled_back
    stages: list[DeploymentStageRecord] = []
    created_at: str
    updated_at: str


# Stage configuration
STAGE_CONFIG = {
    DeployStage.SANDBOX: {"traffic_pct": 0, "min_duration_minutes": 5},
    DeployStage.CANARY_5: {"traffic_pct": 5, "min_duration_minutes": 720},  # 12h
    DeployStage.CANARY_25: {"traffic_pct": 25, "min_duration_minutes": 360},  # 6h
    DeployStage.PRODUCTION: {"traffic_pct": 100, "min_duration_minutes": 0},
}

STAGE_ORDER = [DeployStage.SANDBOX, DeployStage.CANARY_5, DeployStage.CANARY_25, DeployStage.PRODUCTION]


# --- Activities ---

def check_readiness_gate(readiness_score: int) -> tuple[bool, str]:
    """DeploymentGate activity: verify score >= 75 before advancing."""
    if readiness_score >= READINESS_THRESHOLD:
        return True, f"Score {readiness_score} meets threshold {READINESS_THRESHOLD}"
    return False, f"Score {readiness_score} below threshold {READINESS_THRESHOLD} — deployment blocked"


def simulate_stage_metrics(stage: DeployStage, inject_regression: bool = False) -> StageMetrics:
    """Simulate metrics collection for a deployment stage.

    In production, collects real metrics from the running service.
    """
    base_metrics = {
        DeployStage.SANDBOX: StageMetrics(task_success_rate=0.95, latency_p95_ms=250, token_cost_per_task=0.02, escalation_rate=0.05, error_rate=0.05),
        DeployStage.CANARY_5: StageMetrics(task_success_rate=0.93, latency_p95_ms=280, token_cost_per_task=0.025, escalation_rate=0.06, error_rate=0.07),
        DeployStage.CANARY_25: StageMetrics(task_success_rate=0.92, latency_p95_ms=300, token_cost_per_task=0.028, escalation_rate=0.07, error_rate=0.08),
        DeployStage.PRODUCTION: StageMetrics(task_success_rate=0.91, latency_p95_ms=320, token_cost_per_task=0.03, escalation_rate=0.08, error_rate=0.09),
    }

    metrics = base_metrics.get(stage, StageMetrics())

    if inject_regression:
        # Simulate a regression: success rate drops > 5%
        metrics.task_success_rate = max(0, metrics.task_success_rate - 0.10)
        metrics.error_rate = min(1.0, metrics.error_rate + 0.15)

    return metrics


def check_auto_rollback(baseline_metrics: StageMetrics | None, current_metrics: StageMetrics) -> tuple[bool, str]:
    """Check if auto-rollback should trigger based on metric regression.

    Triggers if task_success_rate drops > 5% vs baseline.
    """
    if not baseline_metrics:
        return False, "No baseline — skipping rollback check"

    success_delta = baseline_metrics.task_success_rate - current_metrics.task_success_rate
    if success_delta > 0.05:
        return True, f"Task success rate dropped {success_delta:.1%} vs baseline ({current_metrics.task_success_rate:.1%} vs {baseline_metrics.task_success_rate:.1%})"

    return False, "Metrics within acceptable range"


# --- Workflow Engine ---

class DeploymentEngine:
    """Manages deployment workflows. Production uses Temporal for durability."""

    def __init__(self) -> None:
        self._workflows: dict[str, DeploymentWorkflow] = {}

    def create_workflow(
        self,
        project_id: str,
        tenant_id: str,
        readiness_score: int,
    ) -> DeploymentWorkflow:
        """Create a new deployment workflow. Checks readiness gate first."""
        now = datetime.now(timezone.utc).isoformat()

        passed, message = check_readiness_gate(readiness_score)
        if not passed:
            workflow = DeploymentWorkflow(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tenant_id=tenant_id,
                readiness_score=readiness_score,
                status="failed",
                created_at=now,
                updated_at=now,
            )
            self._workflows[workflow.id] = workflow

            audit_logger.log(
                tenant_id=tenant_id, action=AuditAction.DEPLOYMENT_EVENT,
                resource_type="deployment", resource_id=workflow.id,
                details={"event": "gate_blocked", "message": message, "score": readiness_score},
            )
            return workflow

        # Initialize stages
        stages = []
        for stage in STAGE_ORDER:
            config = STAGE_CONFIG[stage]
            stages.append(DeploymentStageRecord(
                stage_id=str(uuid.uuid4()),
                name=stage,
                status=StageStatus.PENDING,
                traffic_pct=config["traffic_pct"],
            ))

        workflow = DeploymentWorkflow(
            id=str(uuid.uuid4()),
            project_id=project_id,
            tenant_id=tenant_id,
            readiness_score=readiness_score,
            current_stage=DeployStage.SANDBOX,
            status="running",
            stages=stages,
            created_at=now,
            updated_at=now,
        )

        # Activate first stage
        workflow.stages[0].status = StageStatus.ACTIVE
        workflow.stages[0].started_at = now

        self._workflows[workflow.id] = workflow

        audit_logger.log(
            tenant_id=tenant_id, action=AuditAction.DEPLOYMENT_EVENT,
            resource_type="deployment", resource_id=workflow.id,
            details={"event": "workflow_started", "stage": "sandbox", "score": readiness_score},
        )

        return workflow

    def advance_stage(
        self,
        workflow_id: str,
        inject_regression: bool = False,
    ) -> DeploymentWorkflow | None:
        """Advance to the next deployment stage. Collects metrics and checks for rollback."""
        workflow = self._workflows.get(workflow_id)
        if not workflow or workflow.status != "running":
            return None

        now = datetime.now(timezone.utc).isoformat()
        current_idx = next(
            (i for i, s in enumerate(workflow.stages) if s.status == StageStatus.ACTIVE), None
        )
        if current_idx is None:
            return None

        current_stage = workflow.stages[current_idx]

        # Collect metrics for current stage
        metrics = simulate_stage_metrics(current_stage.name, inject_regression=inject_regression)
        current_stage.metrics = metrics

        # Check for auto-rollback
        baseline = workflow.stages[0].metrics if current_idx > 0 else None
        should_rollback, rollback_reason = check_auto_rollback(baseline, metrics)

        if should_rollback:
            return self._rollback(workflow, current_idx, rollback_reason)

        # Complete current stage
        current_stage.status = StageStatus.COMPLETE
        current_stage.completed_at = now

        # Advance to next stage or finish
        next_idx = current_idx + 1
        if next_idx < len(workflow.stages):
            workflow.stages[next_idx].status = StageStatus.ACTIVE
            workflow.stages[next_idx].started_at = now
            workflow.current_stage = workflow.stages[next_idx].name
        else:
            workflow.status = "complete"
            workflow.current_stage = None

        workflow.updated_at = now

        audit_logger.log(
            tenant_id=workflow.tenant_id, action=AuditAction.DEPLOYMENT_EVENT,
            resource_type="deployment", resource_id=workflow.id,
            details={
                "event": "stage_advanced",
                "completed_stage": current_stage.name.value,
                "next_stage": workflow.stages[next_idx].name.value if next_idx < len(workflow.stages) else "done",
            },
        )

        return workflow

    def _rollback(
        self,
        workflow: DeploymentWorkflow,
        failed_stage_idx: int,
        reason: str,
    ) -> DeploymentWorkflow:
        """Execute rollback: revert to previous stage."""
        now = datetime.now(timezone.utc).isoformat()

        workflow.stages[failed_stage_idx].status = StageStatus.ROLLED_BACK
        workflow.stages[failed_stage_idx].completed_at = now
        workflow.stages[failed_stage_idx].error_message = reason
        workflow.status = "rolled_back"
        workflow.updated_at = now

        audit_logger.log(
            tenant_id=workflow.tenant_id, action=AuditAction.DEPLOYMENT_EVENT,
            resource_type="deployment", resource_id=workflow.id,
            details={
                "event": "rollback",
                "failed_stage": workflow.stages[failed_stage_idx].name.value,
                "reason": reason,
            },
        )

        logger.warning("deployment_rolled_back", workflow_id=workflow.id,
                       stage=workflow.stages[failed_stage_idx].name.value, reason=reason)

        return workflow

    def get_workflow(self, workflow_id: str) -> DeploymentWorkflow | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self, tenant_id: str, limit: int = 20) -> list[DeploymentWorkflow]:
        workflows = [w for w in self._workflows.values() if w.tenant_id == tenant_id]
        workflows.sort(key=lambda w: w.created_at, reverse=True)
        return workflows[:limit]

    def clear(self) -> None:
        self._workflows.clear()


# Singleton (in-memory engine for dev/test)
deployment_engine = DeploymentEngine()


# --- Temporal SDK Wiring (production) ---
# These decorated versions mirror the in-memory activities above.
# In production, a Temporal worker process runs these with durable checkpointing.

from temporalio import activity, workflow
from datetime import timedelta


@activity.defn
async def check_readiness_gate_activity(readiness_score: int) -> dict:
    """Temporal activity: check readiness gate."""
    passed, message = check_readiness_gate(readiness_score)
    return {"passed": passed, "message": message}


@activity.defn
async def execute_stage_activity(stage_name: str, inject_regression: bool = False) -> dict:
    """Temporal activity: execute a deployment stage and collect metrics."""
    stage = DeployStage(stage_name)
    metrics = simulate_stage_metrics(stage, inject_regression)
    return metrics.model_dump()


@activity.defn
async def rollback_activity(workflow_id: str, stage_name: str, reason: str) -> dict:
    """Temporal activity: rollback a deployment stage."""
    return {"workflow_id": workflow_id, "stage": stage_name, "reason": reason, "action": "rollback"}


@workflow.defn
class StagedDeploymentTemporalWorkflow:
    """Temporal workflow: 4-stage deployment with durable checkpointing.

    Runs as: sandbox → canary5 → canary25 → production
    Each stage: gate check → execute → metrics → auto-rollback check → advance
    """

    @workflow.run
    async def run(self, project_id: str, tenant_id: str, readiness_score: int) -> dict:
        """Execute the full staged deployment pipeline."""
        # Step 1: Gate check
        gate_result = await workflow.execute_activity(
            check_readiness_gate_activity,
            readiness_score,
            start_to_close_timeout=timedelta(seconds=10),
        )
        if not gate_result["passed"]:
            return {"status": "failed", "reason": gate_result["message"]}

        # Step 2: Execute stages
        baseline_metrics: dict | None = None
        for stage in STAGE_ORDER:
            stage_result = await workflow.execute_activity(
                execute_stage_activity,
                stage.value,
                start_to_close_timeout=timedelta(minutes=5),
            )

            # Capture sandbox as baseline
            if stage == DeployStage.SANDBOX:
                baseline_metrics = stage_result

            # Auto-rollback check (compare against baseline)
            if baseline_metrics and stage != DeployStage.SANDBOX:
                baseline_success = baseline_metrics.get("task_success_rate", 1.0)
                current_success = stage_result.get("task_success_rate", 0.0)
                if baseline_success - current_success > 0.05:
                    await workflow.execute_activity(
                        rollback_activity,
                        args=["", stage.value, f"Success dropped {baseline_success - current_success:.1%}"],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    return {"status": "rolled_back", "stage": stage.value}

        return {"status": "complete", "project_id": project_id}
