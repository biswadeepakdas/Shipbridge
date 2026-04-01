"""Governance routes — audit log, HITL gates, compliance PDF."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.governance.audit import AuditAction, AuditEntry, AuditLogStats, audit_logger
from app.governance.hitl import GateCondition, GateStatus, HumanGate, gate_manager
from app.governance.pdf import ComplianceReport, generate_compliance_report
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


# --- Audit Routes ---

class AuditQueryParams(BaseModel):
    """Query parameters for audit log."""
    action: str | None = None
    resource_type: str | None = None
    limit: int = 50


@router.get("/audit", response_model=APIResponse[list[AuditEntry]])
async def query_audit_log(
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[AuditEntry]]:
    """Query the immutable audit log for the authenticated tenant."""
    action_enum = AuditAction(action) if action else None
    entries = audit_logger.query(
        tenant_id=auth.tenant_id,
        action=action_enum,
        resource_type=resource_type,
        limit=limit,
    )
    return APIResponse(data=entries)


@router.get("/audit/stats", response_model=APIResponse[AuditLogStats])
async def audit_stats(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[AuditLogStats]:
    """Get audit log statistics for the authenticated tenant."""
    stats = audit_logger.get_stats(auth.tenant_id)
    return APIResponse(data=stats)


# --- HITL Gate Routes ---

class GateCreateRequest(BaseModel):
    """Request to create a HITL gate."""
    title: str
    description: str
    resource_type: str
    resource_id: str | None = None
    risk_level: str = "high"
    details: dict = {}


class GateResolveRequest(BaseModel):
    """Request to approve or reject a gate."""
    note: str | None = None


@router.post("/gates", response_model=APIResponse[HumanGate])
async def create_gate(
    body: GateCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[HumanGate]:
    """Create a new HITL approval gate."""
    gate = gate_manager.create_gate(
        tenant_id=auth.tenant_id,
        title=body.title,
        description=body.description,
        requested_by=auth.user_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        risk_level=body.risk_level,
        details=body.details,
    )
    return APIResponse(data=gate)


@router.get("/gates", response_model=APIResponse[list[HumanGate]])
async def list_gates(
    status: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[HumanGate]]:
    """List HITL gates. Filter by status (pending/approved/rejected)."""
    if status == "pending":
        gates = gate_manager.list_pending(auth.tenant_id)
    else:
        gates = gate_manager.list_all(auth.tenant_id)
    return APIResponse(data=gates)


@router.post("/gates/{gate_id}/approve", response_model=APIResponse[HumanGate])
async def approve_gate(
    gate_id: str,
    body: GateResolveRequest = GateResolveRequest(),
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[HumanGate]:
    """Approve a pending HITL gate."""
    gate = gate_manager.approve(gate_id, approved_by=auth.user_id, note=body.note)
    if not gate:
        raise AppError(ErrorCode.NOT_FOUND, f"Gate {gate_id} not found or not pending")
    return APIResponse(data=gate)


@router.post("/gates/{gate_id}/reject", response_model=APIResponse[HumanGate])
async def reject_gate(
    gate_id: str,
    body: GateResolveRequest = GateResolveRequest(),
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[HumanGate]:
    """Reject a pending HITL gate."""
    gate = gate_manager.reject(gate_id, rejected_by=auth.user_id, note=body.note)
    if not gate:
        raise AppError(ErrorCode.NOT_FOUND, f"Gate {gate_id} not found or not pending")
    return APIResponse(data=gate)


# --- Compliance PDF Routes ---

@router.post("/pdf/{project_id}", response_model=APIResponse[ComplianceReport])
async def generate_pdf(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ComplianceReport]:
    """Generate a compliance PDF report for a project."""
    # Get project
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    # Get latest assessment
    assess_result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.project_id == project.id, AssessmentRun.status == "complete")
        .order_by(AssessmentRun.created_at.desc()).limit(1)
    )
    assessment = assess_result.scalar_one_or_none()
    if not assessment:
        raise AppError(ErrorCode.NOT_FOUND, "No completed assessment found")

    audit_stats = audit_logger.get_stats(auth.tenant_id).model_dump()

    report = generate_compliance_report(
        project_name=project.name,
        tenant_name=auth.tenant_id,
        scores_json=assessment.scores_json,
        gap_report_json=assessment.gap_report_json,
        audit_stats=audit_stats,
        generated_by=auth.user_id,
    )

    return APIResponse(data=report)


@router.get("/pdf/{project_id}/html")
async def get_pdf_html(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get the compliance report as rendered HTML (for browser preview or PDF download)."""
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    assess_result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.project_id == project.id, AssessmentRun.status == "complete")
        .order_by(AssessmentRun.created_at.desc()).limit(1)
    )
    assessment = assess_result.scalar_one_or_none()
    if not assessment:
        raise AppError(ErrorCode.NOT_FOUND, "No completed assessment found")

    audit_stats = audit_logger.get_stats(auth.tenant_id).model_dump()

    report = generate_compliance_report(
        project_name=project.name,
        tenant_name=auth.tenant_id,
        scores_json=assessment.scores_json,
        gap_report_json=assessment.gap_report_json,
        audit_stats=audit_stats,
        generated_by=auth.user_id,
    )

    return HTMLResponse(content=report.html)
