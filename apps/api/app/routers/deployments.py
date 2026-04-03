"""Deployment routes — trigger, advance, rollback, status using Temporal."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.deployments import DeploymentStage
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.config import get_settings
from app.workers.temporal_workflows import StagedDeploymentWorkflow

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])

class DeploymentTriggerRequest(BaseModel):
    """Request to start a deployment."""
    project_id: str

async def get_temporal_client() -> Client:
    """FastAPI dependency for Temporal Client."""
    settings = get_settings()
    return await Client.connect(settings.temporal_url)

@router.post("", response_model=APIResponse[dict])
async def trigger_deployment(
    body: DeploymentTriggerRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    temporal: Client = Depends(get_temporal_client),
) -> APIResponse[dict]:
    """Start a staged deployment workflow for a project using Temporal."""
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

    # 3. Start Temporal Workflow
    workflow_id = f"deploy-{project.id}-{uuid.uuid4().hex[:8]}"
    handle = await temporal.start_workflow(
        StagedDeploymentWorkflow.run,
        args=[str(project.id), auth.tenant_id, readiness_score],
        id=workflow_id,
        task_queue="deploy-queue",
    )

    return APIResponse(data={
        "deployment_id": workflow_id,
        "status": "running",
        "project_id": str(project.id),
        "readiness_score": readiness_score,
        "started_at": datetime.now(timezone.utc).isoformat()
    })

@router.get("/{deployment_id}", response_model=APIResponse[dict])
async def get_deployment(
    deployment_id: str,
    temporal: Client = Depends(get_temporal_client),
) -> APIResponse[dict]:
    """Get deployment workflow status from Temporal."""
    handle = temporal.get_workflow_handle(deployment_id)
    desc = await handle.describe()
    
    return APIResponse(data={
        "deployment_id": deployment_id,
        "status": str(desc.status),
        "start_time": desc.start_time.isoformat() if desc.start_time else None,
        "close_time": desc.close_time.isoformat() if desc.close_time else None,
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
