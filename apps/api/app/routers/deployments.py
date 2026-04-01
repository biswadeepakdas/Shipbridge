"""Deployment routes — trigger, advance, rollback, status."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.workers.temporal_workflows import (
    DeploymentWorkflow,
    deployment_engine,
)

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


class DeploymentTriggerRequest(BaseModel):
    """Request to start a deployment."""

    project_id: str


@router.post("", response_model=APIResponse[DeploymentWorkflow])
async def trigger_deployment(
    body: DeploymentTriggerRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DeploymentWorkflow]:
    """Start a staged deployment workflow for a project."""
    # Verify project
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(body.project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {body.project_id} not found")

    # Get latest assessment score
    assess_result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.project_id == project.id, AssessmentRun.status == "complete")
        .order_by(AssessmentRun.created_at.desc()).limit(1)
    )
    assessment = assess_result.scalar_one_or_none()
    readiness_score = assessment.total_score if assessment else 0

    # Use Temporal if configured, otherwise in-memory engine
    from app.config import get_settings
    from datetime import datetime, timezone
    settings = get_settings()
    if settings.use_temporal:
        from app.workers.temporal_workflows import temporal_deployment_client
        wf_id = await temporal_deployment_client.start_deployment(
            project_id=str(project.id), tenant_id=auth.tenant_id, readiness_score=readiness_score,
        )
        now = datetime.now(timezone.utc).isoformat()
        return APIResponse(data=DeploymentWorkflow(
            id=wf_id, project_id=str(project.id), tenant_id=auth.tenant_id,
            readiness_score=readiness_score, status="running", created_at=now, updated_at=now,
        ))

    workflow = deployment_engine.create_workflow(
        project_id=str(project.id),
        tenant_id=auth.tenant_id,
        readiness_score=readiness_score,
    )

    return APIResponse(data=workflow)


@router.post("/{deployment_id}/advance", response_model=APIResponse[DeploymentWorkflow])
async def advance_deployment(
    deployment_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[DeploymentWorkflow]:
    """Advance deployment to the next stage."""
    workflow = deployment_engine.advance_stage(deployment_id)
    if not workflow:
        raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found or not running")
    return APIResponse(data=workflow)


@router.get("/{deployment_id}", response_model=APIResponse[DeploymentWorkflow])
async def get_deployment(
    deployment_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[DeploymentWorkflow]:
    """Get deployment workflow status with all stages."""
    workflow = deployment_engine.get_workflow(deployment_id)
    if not workflow or workflow.tenant_id != auth.tenant_id:
        raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found")
    return APIResponse(data=workflow)


@router.get("/{deployment_id}/stages", response_model=APIResponse[list[dict]])
async def get_deployment_stages(
    deployment_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[dict]]:
    """Get current stages + canary metrics for a deployment."""
    workflow = deployment_engine.get_workflow(deployment_id)
    if not workflow or workflow.tenant_id != auth.tenant_id:
        raise AppError(ErrorCode.NOT_FOUND, f"Deployment {deployment_id} not found")

    return APIResponse(data=[s.model_dump() for s in workflow.stages])


@router.get("", response_model=APIResponse[list[DeploymentWorkflow]])
async def list_deployments(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[DeploymentWorkflow]]:
    """List deployment workflows for the authenticated tenant."""
    workflows = deployment_engine.list_workflows(auth.tenant_id)
    return APIResponse(data=workflows)
