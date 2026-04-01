"""Onboarding routes — wizard steps, framework options, quick-start."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.services.onboarding import (
    OnboardingResult,
    OnboardingStep,
    get_framework_options,
    get_onboarding_steps,
    get_sample_config,
    run_onboarding_assessment,
)

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class QuickStartRequest(BaseModel):
    """Request to complete onboarding in one step."""

    project_name: str
    framework: str = "custom"
    stack_json: dict | None = None


@router.get("/steps", response_model=APIResponse[list[OnboardingStep]])
async def get_steps() -> APIResponse[list[OnboardingStep]]:
    """Get onboarding wizard steps."""
    return APIResponse(data=get_onboarding_steps())


@router.get("/frameworks", response_model=APIResponse[list[dict]])
async def list_frameworks() -> APIResponse[list[dict]]:
    """List available agent frameworks with descriptions."""
    return APIResponse(data=get_framework_options())


@router.get("/sample-config/{framework}", response_model=APIResponse[dict])
async def sample_config(framework: str) -> APIResponse[dict]:
    """Get a sample stack configuration for a framework."""
    config = get_sample_config(framework)
    return APIResponse(data={"framework": framework, "stack_json": config})


@router.post("/quick-start", response_model=APIResponse[OnboardingResult])
async def quick_start(
    body: QuickStartRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[OnboardingResult]:
    """Complete onboarding: create project + run first assessment in one step."""
    stack_json = body.stack_json or get_sample_config(body.framework)

    # Create project
    project = Project(
        tenant_id=uuid.UUID(auth.tenant_id),
        name=body.project_name,
        framework=body.framework,
        stack_json=stack_json,
    )
    db.add(project)
    await db.flush()

    # Run assessment
    result = run_onboarding_assessment(stack_json, body.framework)
    result.project_id = str(project.id)
    result.project_name = body.project_name

    # Store assessment
    from app.assessment.runner import AssessmentRunner
    runner = AssessmentRunner()
    assessment = runner.run(stack_json, body.framework)

    run = AssessmentRun(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        total_score=assessment.total_score,
        scores_json={k: v.model_dump() for k, v in assessment.pillars.items()},
        gap_report_json=assessment.gap_report.model_dump(),
        status="complete",
        triggered_by="onboarding",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    return APIResponse(data=result)
