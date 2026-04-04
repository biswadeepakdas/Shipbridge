"""Deployment routes — trigger, advance, rollback, status.

Uses Temporal when USE_TEMPORAL=true, otherwise falls back to the
in-process DeploymentEngine so local dev and tests work without
a Temporal server.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.deployments import DeploymentStage
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.config import get_settings

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


class DeploymentTriggerRequest(BaseModel):
    """Request to start a deployment."""
    project_id: str


async def _get_temporal_client() -> Any:
    """Connect to Temporal. Only called when USE_TEMPORAL=true."""
    from temporalio.client import Client
    settings = get_settings()
    return await Client.connect(settings.temporal_url)


@router.post("", response_model=APIResponse[dict])
async def trigger_deployment(
    body: DeploymentTriggerRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Start a staged deployment workflow for a project."""
    # 1. Verify project
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(body.project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {body.project_id} not found")

    # 2. Get latest assessment score
    assess_result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.project_id == project.id, AssessmentRun.status == "complete")
        .order_by(AssessmentRun.created_at.desc()).limit(1)
    )
    assessment = assess_result.scalar_one_or_none()
    readiness_score = assessment.total_score if assessment else 0

    settings = get_settings()

    deployment_id: str | None = None
    status_str: str = "running"

    if settings.use_temporal:
        # 3a. Start Temporal Workflow
        from app.workers.temporal_workflows import StagedDeploymentWorkflow
        temporal = await _get_temporal_client()
        workflow_id = f"deploy-{project.id}-{uuid.uuid4().hex[:8]}"
        await temporal.start_workflow(
            StagedDeploymentWorkflow.run,
            args=[str(project.id), auth.tenant_id, readiness_score],
            id=workflow_id,
            task_queue="deploy-queue",
        )
        deployment_id = workflow_id
    else:
        # 3b. In-process engine (dev/test)
        from app.workers.temporal_workflows import deployment_engine, DeployStage
        wf = deployment_engine.create_workflow(
            str(project.id), auth.tenant_id, readiness_score,
        )
        deployment_id = wf.id
        status_str = wf.status

    # Persist initial deployment stages to DeploymentStage table
    stage_names = ["sandbox", "canary5", "canary25", "production"]
    traffic_pcts = [0, 5, 25, 100]
    for stage_name, traffic_pct in zip(stage_names, traffic_pcts):
        stage = DeploymentStage(
            deployment_id=deployment_id,
            tenant_id=uuid.UUID(auth.tenant_id),
            project_id=str(project.id),
            stage_name=stage_name,
            traffic_pct=traffic_pct,
            status="pending",
        )
        db.add(stage)
    await db.commit()

    return APIResponse(data={
        "id": deployment_id,
        "deployment_id": deployment_id,
        "status": status_str,
        "project_id": str(project.id),
        "readiness_score": readiness_score,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/{deployment_id}", response_model=APIResponse[dict])
async def get_deployment(
    deployment_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Get deployment workflow status."""
    settings = get_settings()

    if settings.use_temporal:
        from temporalio.client import Client
        temporal = await _get_temporal_client()
        handle = temporal.get_workflow_handle(deployment_id)
        desc = await handle.describe()
        return APIResponse(data={
            "deployment_id": deployment_id,
            "status": str(desc.status),
            "start_time": desc.start_time.isoformat() if desc.start_time else None,
            "close_time": desc.close_time.isoformat() if desc.close_time else None,
        })
    else:
        from app.workers.temporal_workflows import deployment_engine
        wf = deployment_engine.get_workflow(deployment_id)
        if not wf:
            raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found")
        return APIResponse(data={
            "deployment_id": wf.id,
            "status": wf.status,
            "current_stage": wf.current_stage.value if wf.current_stage else None,
        })


@router.get("", response_model=APIResponse[list])
async def list_deployments(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list]:
    """List deployment history for the authenticated tenant, grouped by deployment_id."""
    tenant_uuid = uuid.UUID(auth.tenant_id)

    # Get the most recent stages, grouped by deployment_id
    result = await db.execute(
        select(DeploymentStage)
        .where(DeploymentStage.tenant_id == tenant_uuid)
        .order_by(DeploymentStage.created_at.desc())
        .limit(100)
    )
    stages = result.scalars().all()

    # Group stages by deployment_id to build deployment summaries
    deployments: dict[str, list[DeploymentStage]] = {}
    for s in stages:
        deployments.setdefault(s.deployment_id, []).append(s)

    items = []
    for dep_id, dep_stages in deployments.items():
        dep_stages.sort(key=lambda s: s.created_at)
        latest = dep_stages[-1]
        completed_count = sum(1 for s in dep_stages if s.status == "completed")
        first_start = next((s.started_at for s in dep_stages if s.started_at), None)
        last_end = next((s.completed_at for s in reversed(dep_stages) if s.completed_at), None)

        duration = ""
        if first_start and last_end:
            delta = last_end - first_start
            minutes = int(delta.total_seconds() // 60)
            duration = f"{minutes}m"

        items.append({
            "id": dep_id,
            "project_id": latest.project_id,
            "status": latest.status,
            "stages_completed": completed_count,
            "stages_total": len(dep_stages),
            "duration": duration,
            "created_at": dep_stages[0].created_at.isoformat(),
        })

    # Sort by created_at descending
    items.sort(key=lambda x: x["created_at"], reverse=True)

    return APIResponse(data=items[:20])


class AdvanceRequest(BaseModel):
    """Optional parameters for advancing a deployment stage."""
    inject_regression: bool = False


@router.post("/{deployment_id}/advance", response_model=APIResponse[dict])
async def advance_deployment(
    deployment_id: str,
    body: AdvanceRequest = AdvanceRequest(),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Advance a deployment to the next stage."""
    settings = get_settings()

    if settings.use_temporal:
        # For Temporal mode, signal the workflow to advance
        temporal = await _get_temporal_client()
        handle = temporal.get_workflow_handle(deployment_id)
        await handle.signal("advance")
        return APIResponse(data={
            "deployment_id": deployment_id,
            "action": "advance_signaled",
        })
    else:
        from app.workers.temporal_workflows import deployment_engine
        wf = deployment_engine.get_workflow(deployment_id)
        if not wf:
            raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found")

        wf = deployment_engine.advance_stage(deployment_id, inject_regression=body.inject_regression)

        # Persist stage result to DeploymentStage table
        for stage in wf.stages:
            result = await db.execute(
                select(DeploymentStage).where(
                    DeploymentStage.deployment_id == deployment_id,
                    DeploymentStage.stage_name == stage.name.value,
                )
            )
            db_stage = result.scalar_one_or_none()
            if db_stage:
                db_stage.status = stage.status.value
                if stage.metrics:
                    db_stage.metrics_json = stage.metrics.model_dump()
                if stage.status.value in ("complete", "failed", "rolled_back"):
                    db_stage.completed_at = datetime.now(timezone.utc)
                if stage.status.value in ("active", "complete"):
                    db_stage.started_at = db_stage.started_at or datetime.now(timezone.utc)

        await db.commit()

        return APIResponse(data={
            "deployment_id": wf.id,
            "status": wf.status,
            "current_stage": wf.current_stage.value if wf.current_stage else None,
            "stages": [
                {
                    "name": s.name.value,
                    "status": s.status.value,
                    "metrics": s.metrics.model_dump() if s.metrics else None,
                }
                for s in wf.stages
            ],
        })


@router.post("/{deployment_id}/rollback", response_model=APIResponse[dict])
async def rollback_deployment(
    deployment_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Rollback the current deployment — sets all remaining stages to rolled_back."""
    settings = get_settings()

    if settings.use_temporal:
        temporal = await _get_temporal_client()
        handle = temporal.get_workflow_handle(deployment_id)
        await handle.signal("rollback")
        return APIResponse(data={
            "deployment_id": deployment_id,
            "action": "rollback_signaled",
        })
    else:
        from app.workers.temporal_workflows import deployment_engine
        wf = deployment_engine.get_workflow(deployment_id)
        if not wf:
            raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found")

        # Rollback: mark all non-complete stages as rolled_back
        from app.workers.temporal_workflows import StageStatus
        for stage in wf.stages:
            if stage.status not in (StageStatus.COMPLETE,):
                stage.status = StageStatus.ROLLED_BACK
        wf.status = "rolled_back"
        wf.current_stage = None

        # Persist to DB
        result = await db.execute(
            select(DeploymentStage).where(
                DeploymentStage.deployment_id == deployment_id,
            )
        )
        db_stages = result.scalars().all()
        for db_stage in db_stages:
            if db_stage.status not in ("completed", "complete"):
                db_stage.status = "rolled_back"
                db_stage.completed_at = datetime.now(timezone.utc)

        await db.commit()

        return APIResponse(data={
            "deployment_id": wf.id,
            "status": "rolled_back",
            "stages": [
                {"name": s.name.value, "status": s.status.value}
                for s in wf.stages
            ],
        })
