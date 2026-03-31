"""Project and assessment routes."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.runner import AssessmentResult, AssessmentRunner
from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


# --- Schemas ---

class ProjectCreate(BaseModel):
    """Request to create a new project."""

    name: str
    framework: str = "custom"
    stack_json: dict = {}
    description: str | None = None
    repo_url: str | None = None


class ProjectOut(BaseModel):
    """Project response."""

    id: str
    name: str
    framework: str
    stack_json: dict
    description: str | None
    repo_url: str | None
    created_at: str


class AssessmentRunOut(BaseModel):
    """Assessment run response."""

    id: str
    project_id: str
    total_score: int
    scores_json: dict
    gap_report_json: dict
    status: str
    created_at: str


# --- Routes ---

@router.post("", response_model=APIResponse[ProjectOut])
async def create_project(
    body: ProjectCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ProjectOut]:
    """Create a new project for the authenticated tenant."""
    project = Project(
        tenant_id=uuid.UUID(auth.tenant_id),
        name=body.name,
        framework=body.framework,
        stack_json=body.stack_json,
        description=body.description,
        repo_url=body.repo_url,
    )
    db.add(project)
    await db.commit()

    return APIResponse(
        data=ProjectOut(
            id=str(project.id),
            name=project.name,
            framework=project.framework,
            stack_json=project.stack_json,
            description=project.description,
            repo_url=project.repo_url,
            created_at=project.created_at.isoformat(),
        )
    )


@router.get("", response_model=APIResponse[list[ProjectOut]])
async def list_projects(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ProjectOut]]:
    """List all projects for the authenticated tenant."""
    result = await db.execute(
        select(Project).where(Project.tenant_id == uuid.UUID(auth.tenant_id))
    )
    projects = result.scalars().all()

    return APIResponse(
        data=[
            ProjectOut(
                id=str(p.id),
                name=p.name,
                framework=p.framework,
                stack_json=p.stack_json,
                description=p.description,
                repo_url=p.repo_url,
                created_at=p.created_at.isoformat(),
            )
            for p in projects
        ]
    )


@router.post("/{project_id}/assess", response_model=APIResponse[AssessmentRunOut])
async def trigger_assessment(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[AssessmentRunOut]:
    """Trigger an assessment run for a project. Returns scored JSON with gap report."""
    # Fetch project with tenant isolation
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    # Run assessment
    runner = AssessmentRunner()
    assessment: AssessmentResult = runner.run(project.stack_json, project.framework)

    # Store results
    run = AssessmentRun(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        total_score=assessment.total_score,
        scores_json={k: v.model_dump() for k, v in assessment.pillars.items()},
        gap_report_json=assessment.gap_report.model_dump(),
        status="complete",
        triggered_by="api",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    return APIResponse(
        data=AssessmentRunOut(
            id=str(run.id),
            project_id=str(run.project_id),
            total_score=run.total_score,
            scores_json=run.scores_json,
            gap_report_json=run.gap_report_json,
            status=run.status,
            created_at=run.created_at.isoformat(),
        )
    )


@router.get("/{project_id}/assessments", response_model=APIResponse[list[AssessmentRunOut]])
async def list_assessments(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[AssessmentRunOut]]:
    """List all assessment runs for a project."""
    result = await db.execute(
        select(AssessmentRun).where(
            AssessmentRun.project_id == uuid.UUID(project_id),
            AssessmentRun.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    runs = result.scalars().all()

    return APIResponse(
        data=[
            AssessmentRunOut(
                id=str(r.id),
                project_id=str(r.project_id),
                total_score=r.total_score,
                scores_json=r.scores_json,
                gap_report_json=r.gap_report_json,
                status=r.status,
                created_at=r.created_at.isoformat(),
            )
            for r in runs
        ]
    )
