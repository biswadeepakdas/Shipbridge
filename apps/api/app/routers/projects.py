"""Project and assessment routes."""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import sqlalchemy
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.readiness_gate import RemediationPlan, evaluate_readiness
from app.assessment.runner import AssessmentResult, AssessmentRunner
from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.deployments import DeploymentStage
from app.models.ingestion import AuditLogEntry, HITLGateRecord, IngestionSource, RuntimeTrace
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

    tenant_uuid = uuid.UUID(auth.tenant_id)
    project_uuid = uuid.UUID(project_id)

    # --- Collect runtime evidence from DB ---
    evidence: dict = {}

    # 1. RuntimeTrace stats
    try:
        # Fetch all traces for this project to compute stats in Python
        trace_result = await db.execute(
            select(RuntimeTrace).where(
                RuntimeTrace.project_id == project_uuid,
                RuntimeTrace.tenant_id == tenant_uuid,
            ).order_by(RuntimeTrace.started_at.desc()).limit(500)
        )
        all_traces = trace_result.scalars().all()
        total = len(all_traces)

        if total > 0:
            ok_count = sum(1 for t in all_traces if t.status == "ok")
            error_count = sum(1 for t in all_traces if t.status == "error")
            avg_duration = sum(t.duration_ms for t in all_traces) / total
            total_input = sum(t.input_tokens for t in all_traces)
            total_output = sum(t.output_tokens for t in all_traces)

            # Approximate p95 latency
            sorted_durations = sorted(t.duration_ms for t in all_traces)
            p95_idx = min(int(total * 0.95), total - 1)
            p95_latency = sorted_durations[p95_idx]

            evidence["traces"] = {
                "total_traces": total,
                "success_rate": ok_count / total,
                "error_rate": error_count / total,
                "avg_duration_ms": round(avg_duration, 1),
                "p95_latency_ms": round(p95_latency, 1),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "tool_failure_rate": 0.0,
            }

            # Tool failure rate
            tool_traces = [t for t in all_traces if t.tool_name is not None]
            if tool_traces:
                tool_errors = sum(1 for t in tool_traces if t.status == "error")
                evidence["traces"]["tool_failure_rate"] = tool_errors / len(tool_traces)

            # Model distribution
            model_counts: dict[str, int] = {}
            for t in all_traces:
                if t.model:
                    model_counts[t.model] = model_counts.get(t.model, 0) + 1
            evidence["traces"]["model_distribution"] = model_counts
    except Exception:
        pass  # Evidence collection is best-effort

    # 2. Latest EvalRun
    try:
        from app.models.evals import EvalRun
        eval_result = await db.execute(
            select(EvalRun)
            .where(EvalRun.project_id == project_uuid)
            .order_by(EvalRun.created_at.desc())
            .limit(1)
        )
        eval_run = eval_result.scalar_one_or_none()
        if eval_run:
            # pass_rate is stored as integer 0-100, convert to 0-1 scale for scorers
            raw_rate = eval_run.pass_rate if hasattr(eval_run, "pass_rate") else 0
            evidence["eval_runs"] = [{
                "pass_rate": raw_rate / 100.0 if raw_rate > 1 else raw_rate,
                "dataset_size": eval_run.dataset_size if hasattr(eval_run, "dataset_size") else 0,
                "status": eval_run.status if hasattr(eval_run, "status") else "unknown",
            }]
    except Exception:
        pass

    # 3. ConnectorHealth (joined through Connector for tenant isolation)
    try:
        from app.models.connectors import Connector, ConnectorHealth
        health_result = await db.execute(
            select(ConnectorHealth)
            .join(Connector, ConnectorHealth.connector_id == Connector.id)
            .where(Connector.tenant_id == tenant_uuid)
            .order_by(ConnectorHealth.checked_at.desc())
            .limit(50)
        )
        health_records = health_result.scalars().all()
        if health_records:
            evidence["connector_health"] = [
                {"status": h.status, "connector_id": str(h.connector_id), "latency_ms": h.latency_ms}
                for h in health_records
            ]
    except Exception:
        pass

    # 4. IngestionSource
    try:
        ing_result = await db.execute(
            select(IngestionSource).where(
                IngestionSource.project_id == project_uuid,
                IngestionSource.tenant_id == tenant_uuid,
            )
        )
        ing_sources = ing_result.scalars().all()
        if ing_sources:
            evidence["ingestion_sources"] = [
                {"mode": s.mode, "config_json": s.config_json, "status": s.status}
                for s in ing_sources
            ]
    except Exception:
        pass

    # 5. DeploymentStage history
    try:
        dep_result = await db.execute(
            select(DeploymentStage)
            .where(DeploymentStage.tenant_id == tenant_uuid)
            .order_by(DeploymentStage.created_at.desc())
            .limit(20)
        )
        dep_stages = dep_result.scalars().all()
        if dep_stages:
            evidence["deployment_history"] = [
                {"stage_name": s.stage_name, "status": s.status, "deployment_id": s.deployment_id}
                for s in dep_stages
            ]
    except Exception:
        pass

    # 6. Audit stats
    try:
        audit_count_result = await db.execute(
            select(func.count(AuditLogEntry.id)).where(AuditLogEntry.tenant_id == tenant_uuid)
        )
        audit_count = audit_count_result.scalar() or 0
        evidence["audit_stats"] = {"total_entries": audit_count}
    except Exception:
        pass

    # 7. HITL gate count
    try:
        hitl_count_result = await db.execute(
            select(func.count(HITLGateRecord.id)).where(HITLGateRecord.tenant_id == tenant_uuid)
        )
        evidence["hitl_gate_count"] = hitl_count_result.scalar() or 0
    except Exception:
        pass

    # Run assessment with evidence
    runner = AssessmentRunner()
    assessment: AssessmentResult = runner.run(
        project.stack_json, project.framework, evidence=evidence or None,
    )

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


@router.get("/{project_id}/assess/stream")
async def stream_assessment(
    project_id: str,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE endpoint for live assessment progress. Streams pillar-by-pillar results."""
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

    runner = AssessmentRunner()

    async def event_generator():
        """Yield SSE events as each pillar is scored."""
        pillars_order = ["reliability", "security", "eval", "governance", "cost"]
        scorers = {
            "reliability": runner.reliability,
            "security": runner.security,
            "eval": runner.eval,
            "governance": runner.governance,
            "cost": runner.cost,
        }

        scored_pillars = {}
        for pillar_name in pillars_order:
            if await request.is_disconnected():
                return

            scorer = scorers[pillar_name]
            pillar_result = scorer.score(project.stack_json, project.framework)
            scored_pillars[pillar_name] = pillar_result

            event_data = {
                "event": "pillar_scored",
                "pillar": pillar_name,
                "score": pillar_result.score,
                "status": pillar_result.status,
                "issues_count": len(pillar_result.issues),
                "progress": len(scored_pillars) / len(pillars_order),
            }
            yield f"data: {json.dumps(event_data)}\n\n"
            await asyncio.sleep(0.1)  # Small delay for visual progress

        # Final result
        assessment = runner.run(project.stack_json, project.framework)
        readiness = evaluate_readiness(assessment)

        # Store in DB
        run = AssessmentRun(
            project_id=project.id,
            tenant_id=uuid.UUID(auth.tenant_id),
            total_score=assessment.total_score,
            scores_json={k: v.model_dump() for k, v in assessment.pillars.items()},
            gap_report_json=assessment.gap_report.model_dump(),
            status="complete",
            triggered_by="sse",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.commit()

        final_data = {
            "event": "assessment_complete",
            "run_id": str(run.id),
            "total_score": assessment.total_score,
            "passed": assessment.passed,
            "gap_report": assessment.gap_report.model_dump(),
            "can_deploy": readiness.can_deploy,
            "remediation_steps": len(readiness.steps),
        }
        yield f"data: {json.dumps(final_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ReadinessGateResponse(BaseModel):
    """Readiness gate check result."""

    can_deploy: bool
    current_score: int
    target_score: int
    gap: int
    remediation_steps: int
    estimated_days: int


@router.get("/{project_id}/readiness", response_model=APIResponse[ReadinessGateResponse])
async def check_readiness(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ReadinessGateResponse]:
    """Check if a project meets the readiness threshold for deployment."""
    # Get latest assessment
    result = await db.execute(
        select(AssessmentRun)
        .where(
            AssessmentRun.project_id == uuid.UUID(project_id),
            AssessmentRun.tenant_id == uuid.UUID(auth.tenant_id),
            AssessmentRun.status == "complete",
        )
        .order_by(AssessmentRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise AppError(ErrorCode.NOT_FOUND, "No completed assessment found. Run an assessment first.")

    # Re-evaluate readiness from stored scores
    from app.assessment.runner import AssessmentResult, GapReport
    from app.assessment.scorers import Issue, PillarScore

    pillars = {
        k: PillarScore(**v) for k, v in run.scores_json.items()
    }
    gap_report = GapReport(**run.gap_report_json)
    assessment = AssessmentResult(
        total_score=run.total_score,
        pillars=pillars,
        gap_report=gap_report,
        passed=run.total_score >= 75,
    )
    readiness = evaluate_readiness(assessment)

    return APIResponse(
        data=ReadinessGateResponse(
            can_deploy=readiness.can_deploy,
            current_score=readiness.current_score,
            target_score=readiness.target_score,
            gap=readiness.gap,
            remediation_steps=len(readiness.steps),
            estimated_days=readiness.estimated_total_days,
        )
    )
