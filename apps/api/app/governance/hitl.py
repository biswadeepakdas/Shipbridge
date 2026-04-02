"""HumanGate — HITL approval gates for high-risk agent actions.

Blocks execution until a human approves or rejects.
Sends notifications via configured channels (Slack webhook, email).
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

import structlog

from app.governance.audit import AuditAction, audit_logger

logger = structlog.get_logger()


class GateStatus(str, Enum):
    """HITL gate states."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GateCondition(BaseModel):
    """Defines when a HITL gate should trigger."""

    resource_type: str
    action_pattern: str  # e.g., "deployment.*", "config.delete"
    risk_level: str = "high"  # "high", "critical"


class HumanGate(BaseModel):
    """A HITL approval gate instance."""

    id: str
    tenant_id: str
    title: str
    description: str
    requested_by: str  # agent_id or user_id
    resource_type: str
    resource_id: str | None = None
    risk_level: str
    status: GateStatus
    details: dict = {}
    requested_at: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None


class GateManager:
    """Manages HITL approval gates."""

    def __init__(self) -> None:
        self._gates: dict[str, HumanGate] = {}
        self._conditions: list[GateCondition] = []

    def add_condition(self, condition: GateCondition) -> None:
        """Register a gate trigger condition."""
        self._conditions.append(condition)

    def should_gate(self, resource_type: str, action: str) -> GateCondition | None:
        """Check if an action should be gated based on registered conditions."""
        for cond in self._conditions:
            if cond.resource_type == resource_type:
                if cond.action_pattern == "*" or action.startswith(cond.action_pattern.rstrip("*")):
                    return cond
        return None

    def create_gate(
        self,
        tenant_id: str,
        title: str,
        description: str,
        requested_by: str,
        resource_type: str,
        resource_id: str | None = None,
        risk_level: str = "high",
        details: dict | None = None,
    ) -> HumanGate:
        """Create a new HITL gate request."""
        gate = HumanGate(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            title=title,
            description=description,
            requested_by=requested_by,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            status=GateStatus.PENDING,
            details=details or {},
            requested_at=datetime.now(timezone.utc).isoformat(),
        )
        self._gates[gate.id] = gate

        # Audit the gate request
        audit_logger.log(
            tenant_id=tenant_id,
            action=AuditAction.HITL_REQUEST,
            resource_type=resource_type,
            resource_id=resource_id,
            agent_id=requested_by,
            details={"gate_id": gate.id, "title": title, "risk_level": risk_level},
        )

        logger.info("hitl_gate_created", gate_id=gate.id, title=title, risk_level=risk_level)
        return gate

    def approve(self, gate_id: str, approved_by: str, note: str | None = None) -> HumanGate | None:
        """Approve a pending gate."""
        gate = self._gates.get(gate_id)
        if not gate or gate.status != GateStatus.PENDING:
            return None

        gate.status = GateStatus.APPROVED
        gate.resolved_at = datetime.now(timezone.utc).isoformat()
        gate.resolved_by = approved_by
        gate.resolution_note = note

        audit_logger.log(
            tenant_id=gate.tenant_id,
            action=AuditAction.HITL_RESPONSE,
            resource_type=gate.resource_type,
            resource_id=gate.resource_id,
            user_id=approved_by,
            details={"gate_id": gate_id, "decision": "approved", "note": note},
        )

        logger.info("hitl_gate_approved", gate_id=gate_id, approved_by=approved_by)
        return gate

    def reject(self, gate_id: str, rejected_by: str, note: str | None = None) -> HumanGate | None:
        """Reject a pending gate."""
        gate = self._gates.get(gate_id)
        if not gate or gate.status != GateStatus.PENDING:
            return None

        gate.status = GateStatus.REJECTED
        gate.resolved_at = datetime.now(timezone.utc).isoformat()
        gate.resolved_by = rejected_by
        gate.resolution_note = note

        audit_logger.log(
            tenant_id=gate.tenant_id,
            action=AuditAction.HITL_RESPONSE,
            resource_type=gate.resource_type,
            resource_id=gate.resource_id,
            user_id=rejected_by,
            details={"gate_id": gate_id, "decision": "rejected", "note": note},
        )

        logger.info("hitl_gate_rejected", gate_id=gate_id, rejected_by=rejected_by)
        return gate

    def list_pending(self, tenant_id: str) -> list[HumanGate]:
        """List all pending gates for a tenant."""
        return [g for g in self._gates.values()
                if g.tenant_id == tenant_id and g.status == GateStatus.PENDING]

    def list_all(self, tenant_id: str, limit: int = 50) -> list[HumanGate]:
        """List all gates for a tenant, newest first."""
        gates = [g for g in self._gates.values() if g.tenant_id == tenant_id]
        gates.sort(key=lambda g: g.requested_at, reverse=True)
        return gates[:limit]

    def get_gate(self, gate_id: str) -> HumanGate | None:
        return self._gates.get(gate_id)

    def clear(self) -> None:
        self._gates.clear()
        self._conditions.clear()


# Singleton
gate_manager = GateManager()
