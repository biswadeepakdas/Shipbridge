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


# Singleton — in-memory fallback
gate_manager = GateManager()


class PersistentGateManager:
    """Database-backed HITL gate manager using HITLGateRecord model."""

    async def create_gate(
        self,
        db,
        tenant_id: str,
        title: str,
        description: str,
        requested_by: str,
        resource_type: str,
        resource_id: str | None = None,
        risk_level: str = "high",
        details: dict | None = None,
    ) -> HumanGate:
        """Create a new HITL gate in the database."""
        from app.models.ingestion import HITLGateRecord

        record = HITLGateRecord(
            tenant_id=uuid.UUID(tenant_id),
            title=title,
            description=description,
            requested_by=requested_by,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            status="pending",
            details_json=details or {},
        )
        db.add(record)
        await db.commit()

        logger.info("hitl_gate_created_persistent", gate_id=str(record.id), title=title)

        return HumanGate(
            id=str(record.id),
            tenant_id=tenant_id,
            title=title,
            description=description,
            requested_by=requested_by,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            status=GateStatus.PENDING,
            details=details or {},
            requested_at=record.requested_at.isoformat(),
        )

    async def approve(self, db, gate_id: str, approved_by: str, note: str | None = None) -> HumanGate | None:
        """Approve a pending gate in the database."""
        from sqlalchemy import select
        from app.models.ingestion import HITLGateRecord

        result = await db.execute(
            select(HITLGateRecord).where(
                HITLGateRecord.id == uuid.UUID(gate_id),
                HITLGateRecord.status == "pending",
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        record.status = "approved"
        record.resolved_at = datetime.now(timezone.utc)
        record.resolved_by = approved_by
        record.resolution_note = note
        await db.commit()

        logger.info("hitl_gate_approved_persistent", gate_id=gate_id, approved_by=approved_by)
        return self._record_to_gate(record)

    async def reject(self, db, gate_id: str, rejected_by: str, note: str | None = None) -> HumanGate | None:
        """Reject a pending gate in the database."""
        from sqlalchemy import select
        from app.models.ingestion import HITLGateRecord

        result = await db.execute(
            select(HITLGateRecord).where(
                HITLGateRecord.id == uuid.UUID(gate_id),
                HITLGateRecord.status == "pending",
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        record.status = "rejected"
        record.resolved_at = datetime.now(timezone.utc)
        record.resolved_by = rejected_by
        record.resolution_note = note
        await db.commit()

        logger.info("hitl_gate_rejected_persistent", gate_id=gate_id, rejected_by=rejected_by)
        return self._record_to_gate(record)

    async def list_pending(self, db, tenant_id: str) -> list[HumanGate]:
        """List all pending gates for a tenant from the database."""
        from sqlalchemy import select
        from app.models.ingestion import HITLGateRecord

        result = await db.execute(
            select(HITLGateRecord).where(
                HITLGateRecord.tenant_id == uuid.UUID(tenant_id),
                HITLGateRecord.status == "pending",
            ).order_by(HITLGateRecord.requested_at.desc())
        )
        records = result.scalars().all()
        return [self._record_to_gate(r) for r in records]

    async def list_all(self, db, tenant_id: str, limit: int = 50) -> list[HumanGate]:
        """List all gates for a tenant from the database."""
        from sqlalchemy import select
        from app.models.ingestion import HITLGateRecord

        result = await db.execute(
            select(HITLGateRecord).where(
                HITLGateRecord.tenant_id == uuid.UUID(tenant_id),
            ).order_by(HITLGateRecord.requested_at.desc()).limit(limit)
        )
        records = result.scalars().all()
        return [self._record_to_gate(r) for r in records]

    @staticmethod
    def _record_to_gate(record) -> HumanGate:
        return HumanGate(
            id=str(record.id),
            tenant_id=str(record.tenant_id),
            title=record.title,
            description=record.description,
            requested_by=record.requested_by,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            risk_level=record.risk_level,
            status=GateStatus(record.status),
            details=record.details_json,
            requested_at=record.requested_at.isoformat(),
            resolved_at=record.resolved_at.isoformat() if record.resolved_at else None,
            resolved_by=record.resolved_by,
            resolution_note=record.resolution_note,
        )


# Singleton persistent gate manager
persistent_gate_manager = PersistentGateManager()


def get_gate_manager(db=None):
    """Factory: returns PersistentGateManager when DB is available, falls back to in-memory."""
    if db is not None:
        return persistent_gate_manager
    return gate_manager
