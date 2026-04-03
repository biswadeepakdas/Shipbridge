"""Events routes — list recent agent events with pipeline stats."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.middleware.auth import AuthContext, get_auth_context
from app.models.events import AgentEvent
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=APIResponse[dict])
async def list_events(
    limit: int = Query(default=50, le=200),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """List recent events for the authenticated tenant with pipeline stats."""
    tenant_uuid = uuid.UUID(auth.tenant_id)

    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.tenant_id == tenant_uuid)
        .order_by(AgentEvent.received_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    items = [
        {
            "id": str(e.id),
            "provider": e.source,
            "event_type": e.event_type,
            "status": "processed",
            "tenant_id": str(e.tenant_id),
            "created_at": e.received_at.isoformat() if e.received_at else e.occurred_at.isoformat(),
            "dedup_key": e.dedup_key or "",
        }
        for e in events
    ]

    # Compute today's stats from the fetched window
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_events = [e for e in events if e.received_at and e.received_at >= today_start]

    # Count today's total via a lightweight DB query for accuracy
    count_result = await db.execute(
        select(func.count())
        .select_from(AgentEvent)
        .where(
            AgentEvent.tenant_id == tenant_uuid,
            AgentEvent.received_at >= today_start,
        )
    )
    events_today = count_result.scalar() or 0

    return APIResponse(data={
        "events": items,
        "stats": {
            "events_today": events_today,
            "dedup_rate": 0.0,
            "unknown_queue_size": 0,
            "dlq_size": 0,
        },
    })
