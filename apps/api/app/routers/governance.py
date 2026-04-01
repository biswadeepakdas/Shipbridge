"""Governance routes — audit log, HITL gates, approval/reject."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.exceptions import AppError, ErrorCode
from app.governance.audit import AuditAction, AuditEntry, AuditLogStats, audit_logger
from app.governance.hitl import GateCondition, GateStatus, HumanGate, gate_manager
from app.middleware.auth import AuthContext, get_auth_context
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
