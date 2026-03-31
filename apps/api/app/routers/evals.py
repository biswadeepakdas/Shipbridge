"""Eval harness routes — generate test suites, capture baselines, list runs."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.evals import EvalBaseline, EvalRun
from app.models.projects import Project
from app.schemas.response import APIResponse
from app.services.eval_harness import (
    EvalHarnessOutput,
    generate_eval_harness,
)

router = APIRouter(prefix="/api/v1/projects", tags=["evals"])


# --- Schemas ---

class GenerateHarnessRequest(BaseModel):
    """Optional overrides for harness generation."""

    num_cases: int = 20
    threshold: int = 75


class EvalRunOut(BaseModel):
    """Eval run response."""

    id: str
    project_id: str
    pass_rate: int
    dataset_size: int
    scores_json: dict
    baseline_delta: dict | None
    status: str
    triggered_by: str
    created_at: str


class EvalBaselineOut(BaseModel):
    """Eval baseline response."""

    id: str
    project_id: str
    scores_json: dict
    dataset_snapshot: dict
    is_active: bool
    created_at: str


# --- Routes ---

@router.post("/{project_id}/eval/generate", response_model=APIResponse[EvalHarnessOutput])
async def generate_harness(
    project_id: str,
    body: GenerateHarnessRequest = GenerateHarnessRequest(),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[EvalHarnessOutput]:
    """Generate a complete eval harness for a project: dataset, grader, CI gate, baseline."""
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    tools = project.stack_json.get("tools", [])
    harness = generate_eval_harness(
        project_name=project.name,
        framework=project.framework,
        tools=tools,
        num_cases=body.num_cases,
        threshold=body.threshold,
    )

    # Store as eval run + baseline
    eval_run = EvalRun(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        scores_json=harness.baseline.scores,
        dataset_size=harness.dataset.total_cases,
        pass_rate=int(harness.baseline.pass_rate * 100),
        triggered_by="harness_gen",
        status="complete",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(eval_run)
    await db.flush()

    baseline = EvalBaseline(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        eval_run_id=eval_run.id,
        scores_json=harness.baseline.scores,
        dataset_snapshot={
            "total_cases": harness.dataset.total_cases,
            "categories": harness.dataset.categories,
            "pass_rate": harness.baseline.pass_rate,
        },
    )
    db.add(baseline)
    await db.commit()

    return APIResponse(data=harness)


@router.get("/{project_id}/eval/runs", response_model=APIResponse[list[EvalRunOut]])
async def list_eval_runs(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[EvalRunOut]]:
    """List all eval runs for a project."""
    result = await db.execute(
        select(EvalRun).where(
            EvalRun.project_id == uuid.UUID(project_id),
            EvalRun.tenant_id == uuid.UUID(auth.tenant_id),
        ).order_by(EvalRun.created_at.desc())
    )
    runs = result.scalars().all()

    return APIResponse(
        data=[
            EvalRunOut(
                id=str(r.id),
                project_id=str(r.project_id),
                pass_rate=r.pass_rate,
                dataset_size=r.dataset_size,
                scores_json=r.scores_json,
                baseline_delta=r.baseline_delta,
                status=r.status,
                triggered_by=r.triggered_by,
                created_at=r.created_at.isoformat(),
            )
            for r in runs
        ]
    )


@router.get("/{project_id}/eval/baseline", response_model=APIResponse[EvalBaselineOut | None])
async def get_active_baseline(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[EvalBaselineOut | None]:
    """Get the active baseline for a project."""
    result = await db.execute(
        select(EvalBaseline).where(
            EvalBaseline.project_id == uuid.UUID(project_id),
            EvalBaseline.tenant_id == uuid.UUID(auth.tenant_id),
            EvalBaseline.is_active.is_(True),
        ).order_by(EvalBaseline.created_at.desc()).limit(1)
    )
    baseline = result.scalar_one_or_none()

    if not baseline:
        return APIResponse(data=None)

    return APIResponse(
        data=EvalBaselineOut(
            id=str(baseline.id),
            project_id=str(baseline.project_id),
            scores_json=baseline.scores_json,
            dataset_snapshot=baseline.dataset_snapshot,
            is_active=baseline.is_active,
            created_at=baseline.created_at.isoformat(),
        )
    )


@router.get("/{project_id}/eval/ci-gate")
async def download_ci_gate(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Get the CI gate YAML template for download."""
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    from app.services.eval_harness import generate_ci_gate_template
    ci_gate = generate_ci_gate_template(project.name)

    return APIResponse(data={
        "filename": ci_gate.filename,
        "yaml_content": ci_gate.yaml_content,
        "score_threshold": ci_gate.score_threshold,
    })
