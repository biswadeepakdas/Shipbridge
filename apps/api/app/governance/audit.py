"""AuditLogger — immutable append-only audit log for all agent actions.

Every tool call, LLM decision, and state change is logged.
No UPDATE or DELETE allowed on audit records.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class AuditAction(str, Enum):
    """Types of auditable actions."""

    TOOL_CALL = "tool_call"
    LLM_DECISION = "llm_decision"
    STATE_CHANGE = "state_change"
    AUTH_EVENT = "auth_event"
    DEPLOYMENT_EVENT = "deployment_event"
    HITL_REQUEST = "hitl_request"
    HITL_RESPONSE = "hitl_response"
    CONFIG_CHANGE = "config_change"
    DATA_ACCESS = "data_access"


class AuditEntry(BaseModel):
    """A single immutable audit log entry."""

    id: str
    tenant_id: str
    user_id: str | None = None
    agent_id: str | None = None
    action: AuditAction
    resource_type: str
    resource_id: str | None = None
    details: dict = {}
    ip_address: str | None = None
    trace_id: str | None = None
    created_at: str


class AuditLogStats(BaseModel):
    """Audit log summary statistics."""

    total_entries: int
    entries_last_7d: int
    actions_by_type: dict[str, int]
    most_active_agents: list[dict]


class AuditLogger:
    """Immutable append-only audit logger.

    In production, backed by a Postgres table with RLS preventing UPDATE/DELETE.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def log(
        self,
        tenant_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEntry:
        """Append an audit entry. Returns the created entry."""
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            trace_id=trace_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(entry)

        logger.info("audit_logged", action=action.value, resource_type=resource_type,
                    resource_id=resource_id, tenant_id=tenant_id)
        return entry

    def query(
        self,
        tenant_id: str,
        action: AuditAction | None = None,
        resource_type: str | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit entries. Immutable — read-only access."""
        results = [e for e in reversed(self._entries) if e.tenant_id == tenant_id]
        if action:
            results = [e for e in results if e.action == action]
        if resource_type:
            results = [e for e in results if e.resource_type == resource_type]
        return results[:limit]

    def get_stats(self, tenant_id: str) -> AuditLogStats:
        """Get audit log statistics for a tenant."""
        tenant_entries = [e for e in self._entries if e.tenant_id == tenant_id]

        actions_by_type: dict[str, int] = {}
        agent_counts: dict[str, int] = {}

        for entry in tenant_entries:
            actions_by_type[entry.action.value] = actions_by_type.get(entry.action.value, 0) + 1
            if entry.agent_id:
                agent_counts[entry.agent_id] = agent_counts.get(entry.agent_id, 0) + 1

        most_active = sorted(
            [{"agent_id": k, "action_count": v} for k, v in agent_counts.items()],
            key=lambda x: x["action_count"], reverse=True,
        )[:5]

        return AuditLogStats(
            total_entries=len(tenant_entries),
            entries_last_7d=len(tenant_entries),  # simplified — all in-memory
            actions_by_type=actions_by_type,
            most_active_agents=most_active,
        )

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """Clear for testing only. In production, audit logs are never deleted."""
        self._entries.clear()


# Singleton — in-memory fallback
audit_logger = AuditLogger()


class PersistentAuditLogger:
    """Database-backed audit logger using AuditLogEntry model."""

    async def log(
        self,
        db,
        tenant_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEntry:
        """Write an audit entry to the database and return a Pydantic model."""
        from app.models.ingestion import AuditLogEntry

        entry = AuditLogEntry(
            tenant_id=uuid.UUID(tenant_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            agent_id=agent_id,
            action=action.value,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=details or {},
            ip_address=ip_address,
            trace_id=trace_id,
        )
        db.add(entry)
        await db.commit()

        logger.info("audit_logged_persistent", action=action.value, resource_type=resource_type,
                    resource_id=resource_id, tenant_id=tenant_id)

        return AuditEntry(
            id=str(entry.id),
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            trace_id=trace_id,
            created_at=entry.created_at.isoformat(),
        )

    async def query(
        self,
        db,
        tenant_id: str,
        action: AuditAction | None = None,
        resource_type: str | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit entries from the database."""
        from sqlalchemy import select
        from app.models.ingestion import AuditLogEntry

        query = select(AuditLogEntry).where(
            AuditLogEntry.tenant_id == uuid.UUID(tenant_id)
        )
        if action:
            query = query.where(AuditLogEntry.action == action.value)
        if resource_type:
            query = query.where(AuditLogEntry.resource_type == resource_type)

        query = query.order_by(AuditLogEntry.created_at.desc()).limit(limit)
        result = await db.execute(query)
        rows = result.scalars().all()

        return [
            AuditEntry(
                id=str(r.id),
                tenant_id=str(r.tenant_id),
                user_id=str(r.user_id) if r.user_id else None,
                agent_id=r.agent_id,
                action=AuditAction(r.action),
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                details=r.details_json,
                ip_address=r.ip_address,
                trace_id=r.trace_id,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]

    async def get_stats(self, db, tenant_id: str) -> AuditLogStats:
        """Get audit log statistics from the database."""
        from sqlalchemy import func, select
        from app.models.ingestion import AuditLogEntry

        # Total count
        total_result = await db.execute(
            select(func.count(AuditLogEntry.id)).where(
                AuditLogEntry.tenant_id == uuid.UUID(tenant_id)
            )
        )
        total = total_result.scalar() or 0

        # Actions by type
        action_result = await db.execute(
            select(AuditLogEntry.action, func.count(AuditLogEntry.id))
            .where(AuditLogEntry.tenant_id == uuid.UUID(tenant_id))
            .group_by(AuditLogEntry.action)
        )
        actions_by_type = {row[0]: row[1] for row in action_result.all()}

        # Most active agents
        agent_result = await db.execute(
            select(AuditLogEntry.agent_id, func.count(AuditLogEntry.id))
            .where(
                AuditLogEntry.tenant_id == uuid.UUID(tenant_id),
                AuditLogEntry.agent_id.isnot(None),
            )
            .group_by(AuditLogEntry.agent_id)
            .order_by(func.count(AuditLogEntry.id).desc())
            .limit(5)
        )
        most_active = [
            {"agent_id": row[0], "action_count": row[1]}
            for row in agent_result.all()
        ]

        return AuditLogStats(
            total_entries=total,
            entries_last_7d=total,  # simplified
            actions_by_type=actions_by_type,
            most_active_agents=most_active,
        )


# Singleton persistent logger
persistent_audit_logger = PersistentAuditLogger()


def get_audit_logger(db=None):
    """Factory: returns PersistentAuditLogger when DB is available, falls back to in-memory."""
    if db is not None:
        return persistent_audit_logger
    return audit_logger
