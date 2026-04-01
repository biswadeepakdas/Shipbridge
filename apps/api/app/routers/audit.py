"""Audit trail endpoints — retrieve and export per-project agent decision logs."""

import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/projects", tags=["audit"])


@router.get("/{project_id}/audit-trail")
async def get_audit_trail(project_id: str, request: Request, tenant_id: str = "default"):
    """Returns the last 100 audit trail entries for a project."""
    redis = request.app.state.redis
    raw_entries = await redis.lrange(f"audit:{tenant_id}:{project_id}", 0, 99)
    entries = []
    for entry in raw_entries:
        try:
            entries.append(json.loads(entry.decode() if isinstance(entry, bytes) else entry))
        except Exception:
            pass
    return {"project_id": project_id, "tenant_id": tenant_id, "entries": entries, "count": len(entries)}


@router.get("/{project_id}/audit-trail/export")
async def export_audit_trail(project_id: str, request: Request, tenant_id: str = "default"):
    """Exports the full audit trail as a downloadable JSON file."""
    redis = request.app.state.redis
    raw_entries = await redis.lrange(f"audit:{tenant_id}:{project_id}", 0, -1)
    entries = []
    for entry in raw_entries:
        try:
            entries.append(json.loads(entry.decode() if isinstance(entry, bytes) else entry))
        except Exception:
            pass
    payload = json.dumps({"project_id": project_id, "tenant_id": tenant_id, "entries": entries}, indent=2)
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=audit-trail-{project_id}.json"},
    )
