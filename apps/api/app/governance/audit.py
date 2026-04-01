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


# Singleton
audit_logger = AuditLogger()
