"""Ingestion routes — register, validate, and manage agent ingestion sources and traces."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.ingestion.manifest_parser import (
    ManifestValidationResult,
    manifest_to_stack_json,
    parse_manifest,
)
from app.ingestion.validator import (
    validate_github_repo,
    validate_manifest,
    validate_runtime_endpoint,
)
from app.middleware.auth import AuthContext, get_auth_context
from app.models.ingestion import IngestionSource, RuntimeTrace
from app.models.projects import Project
from app.schemas.response import APIResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IngestionCreateRequest(BaseModel):
    """Request to register a new ingestion source."""

    mode: str  # github_repo | runtime_endpoint | sdk_instrumentation | manifest
    config: dict = {}


class IngestionSourceOut(BaseModel):
    id: str
    project_id: str
    mode: str
    config_json: dict
    status: str
    validation_result: dict | None
    last_synced_at: str | None
    created_at: str


class TraceIngestRequest(BaseModel):
    """Batch of runtime traces from SDK."""

    traces: list[dict]


class RuntimeTraceOut(BaseModel):
    id: str
    trace_id: str
    span_id: str
    operation: str
    status: str
    duration_ms: float
    model: str | None
    tool_name: str | None
    error_message: str | None
    input_tokens: int
    output_tokens: int
    started_at: str
    created_at: str


class ManifestValidateRequest(BaseModel):
    yaml_content: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_to_out(src: IngestionSource) -> IngestionSourceOut:
    return IngestionSourceOut(
        id=str(src.id),
        project_id=str(src.project_id),
        mode=src.mode,
        config_json=src.config_json,
        status=src.status,
        validation_result=src.validation_result,
        last_synced_at=src.last_synced_at.isoformat() if src.last_synced_at else None,
        created_at=src.created_at.isoformat(),
    )


def _trace_to_out(t: RuntimeTrace) -> RuntimeTraceOut:
    return RuntimeTraceOut(
        id=str(t.id),
        trace_id=t.trace_id,
        span_id=t.span_id,
        operation=t.operation,
        status=t.status,
        duration_ms=t.duration_ms,
        model=t.model,
        tool_name=t.tool_name,
        error_message=t.error_message,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        started_at=t.started_at.isoformat(),
        created_at=t.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Ingestion Source Routes
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/ingestion",
    response_model=APIResponse[IngestionSourceOut],
)
async def register_ingestion_source(
    project_id: str,
    body: IngestionCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[IngestionSourceOut]:
    """Register a new ingestion source for a project."""
    # Verify project
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    valid_modes = {"github_repo", "runtime_endpoint", "sdk_instrumentation", "manifest"}
    if body.mode not in valid_modes:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Invalid mode. Must be one of: {valid_modes}")

    # Validate based on mode
    validation: dict | None = None
    status = "pending"

    if body.mode == "github_repo":
        repo_url = body.config.get("repo_url", "")
        if not repo_url:
            raise AppError(ErrorCode.VALIDATION_ERROR, "config.repo_url is required for github_repo mode")
        validation = await validate_github_repo(repo_url)
        status = "active" if validation.get("valid") else "failed"
        # Update project repo_url
        if validation.get("valid"):
            project.repo_url = repo_url
            repo_info = validation.get("repo_info", {})
            body.config["repo_info"] = repo_info

    elif body.mode == "runtime_endpoint":
        endpoint_url = body.config.get("endpoint_url", "")
        if not endpoint_url:
            raise AppError(ErrorCode.VALIDATION_ERROR, "config.endpoint_url is required for runtime_endpoint mode")
        auth_header = body.config.get("auth_header")
        validation = await validate_runtime_endpoint(endpoint_url, auth_header)
        status = "active" if validation.get("valid") else "failed"

    elif body.mode == "sdk_instrumentation":
        # SDK mode is always valid — user just needs the setup instructions
        status = "active"
        validation = {
            "valid": True,
            "setup_instructions": {
                "install": "pip install shipbridge-sdk",
                "code_snippet": (
                    "from shipbridge import ShipBridgeClient\n\n"
                    f'client = ShipBridgeClient(\n    api_url="{auth.tenant_id}",\n'
                    f'    project_id="{project_id}",\n'
                    '    api_key="YOUR_API_KEY"\n)\n\n'
                    "# Wrap agent calls with tracing\n"
                    'with client.trace("agent_call", model="claude-3-5-sonnet"):\n'
                    "    result = your_agent.run(input_data)\n"
                ),
            },
        }

    elif body.mode == "manifest":
        yaml_content = body.config.get("manifest_yaml", "")
        if not yaml_content:
            raise AppError(ErrorCode.VALIDATION_ERROR, "config.manifest_yaml is required for manifest mode")
        manifest_result = await validate_manifest(yaml_content)
        validation = manifest_result.model_dump()
        status = "active" if manifest_result.valid else "failed"
        # If valid, update project stack_json from manifest
        if manifest_result.valid and manifest_result.manifest:
            m = manifest_result.manifest
            project.stack_json = manifest_to_stack_json(m)
            project.framework = m.framework
            if m.description:
                project.description = m.description

    source = IngestionSource(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        mode=body.mode,
        config_json=body.config,
        status=status,
        validation_result=validation,
        last_synced_at=datetime.now(timezone.utc) if status == "active" else None,
    )
    db.add(source)
    await db.commit()

    logger.info("ingestion_source_registered", project_id=project_id, mode=body.mode, status=status)
    return APIResponse(data=_source_to_out(source))


@router.get(
    "/projects/{project_id}/ingestion",
    response_model=APIResponse[list[IngestionSourceOut]],
)
async def list_ingestion_sources(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[IngestionSourceOut]]:
    """List ingestion sources for a project."""
    result = await db.execute(
        select(IngestionSource).where(
            IngestionSource.project_id == uuid.UUID(project_id),
            IngestionSource.tenant_id == uuid.UUID(auth.tenant_id),
        ).order_by(IngestionSource.created_at.desc())
    )
    sources = result.scalars().all()
    return APIResponse(data=[_source_to_out(s) for s in sources])


@router.post(
    "/projects/{project_id}/ingestion/{source_id}/validate",
    response_model=APIResponse[IngestionSourceOut],
)
async def revalidate_source(
    project_id: str,
    source_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[IngestionSourceOut]:
    """Re-validate an existing ingestion source."""
    result = await db.execute(
        select(IngestionSource).where(
            IngestionSource.id == uuid.UUID(source_id),
            IngestionSource.project_id == uuid.UUID(project_id),
            IngestionSource.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise AppError(ErrorCode.NOT_FOUND, "Ingestion source not found")

    source.status = "validating"
    validation: dict | None = None

    if source.mode == "github_repo":
        validation = await validate_github_repo(source.config_json.get("repo_url", ""))
    elif source.mode == "runtime_endpoint":
        validation = await validate_runtime_endpoint(
            source.config_json.get("endpoint_url", ""),
            source.config_json.get("auth_header"),
        )
    elif source.mode == "manifest":
        yaml_content = source.config_json.get("manifest_yaml", "")
        mr = await validate_manifest(yaml_content)
        validation = mr.model_dump()
    elif source.mode == "sdk_instrumentation":
        validation = {"valid": True, "message": "SDK mode is always active"}

    valid = validation.get("valid", False) if validation else False
    source.status = "active" if valid else "failed"
    source.validation_result = validation
    if valid:
        source.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    return APIResponse(data=_source_to_out(source))


# ---------------------------------------------------------------------------
# Trace Ingestion Routes
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/traces",
    response_model=APIResponse[dict],
)
async def ingest_traces(
    project_id: str,
    body: TraceIngestRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Ingest a batch of runtime traces from the SDK or OTel exporter."""
    # Verify project
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    if not result.scalar_one_or_none():
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    ingested = 0
    errors_list: list[str] = []

    for i, t in enumerate(body.traces):
        try:
            trace = RuntimeTrace(
                project_id=uuid.UUID(project_id),
                tenant_id=uuid.UUID(auth.tenant_id),
                trace_id=t.get("trace_id", str(uuid.uuid4())),
                span_id=t.get("span_id", str(uuid.uuid4())),
                parent_span_id=t.get("parent_span_id"),
                operation=t.get("operation", "unknown"),
                status=t.get("status", "ok"),
                duration_ms=float(t.get("duration_ms", 0)),
                input_tokens=int(t.get("input_tokens", 0)),
                output_tokens=int(t.get("output_tokens", 0)),
                model=t.get("model"),
                tool_name=t.get("tool_name"),
                error_message=t.get("error_message"),
                metadata_json=t.get("metadata", {}),
                started_at=datetime.fromisoformat(t["started_at"]) if "started_at" in t else datetime.now(timezone.utc),
            )
            db.add(trace)
            ingested += 1
        except Exception as exc:
            errors_list.append(f"trace[{i}]: {exc}")

    await db.commit()

    logger.info("traces_ingested", project_id=project_id, count=ingested, errors=len(errors_list))
    return APIResponse(data={"ingested": ingested, "errors": errors_list})


@router.get(
    "/projects/{project_id}/traces",
    response_model=APIResponse[dict],
)
async def list_traces(
    project_id: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    operation: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Query traces for a project with optional filters."""
    query = select(RuntimeTrace).where(
        RuntimeTrace.project_id == uuid.UUID(project_id),
        RuntimeTrace.tenant_id == uuid.UUID(auth.tenant_id),
    )
    if status:
        query = query.where(RuntimeTrace.status == status)
    if operation:
        query = query.where(RuntimeTrace.operation == operation)

    query = query.order_by(RuntimeTrace.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    traces = result.scalars().all()

    # Stats
    stats_query = select(
        func.count(RuntimeTrace.id).label("total"),
        func.avg(RuntimeTrace.duration_ms).label("avg_duration_ms"),
        func.sum(RuntimeTrace.input_tokens).label("total_input_tokens"),
        func.sum(RuntimeTrace.output_tokens).label("total_output_tokens"),
    ).where(
        RuntimeTrace.project_id == uuid.UUID(project_id),
        RuntimeTrace.tenant_id == uuid.UUID(auth.tenant_id),
    )
    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one_or_none()

    error_count_result = await db.execute(
        select(func.count(RuntimeTrace.id)).where(
            RuntimeTrace.project_id == uuid.UUID(project_id),
            RuntimeTrace.tenant_id == uuid.UUID(auth.tenant_id),
            RuntimeTrace.status == "error",
        )
    )
    error_count = error_count_result.scalar() or 0

    total = stats_row.total if stats_row else 0

    return APIResponse(data={
        "traces": [_trace_to_out(t) for t in traces],
        "stats": {
            "total_traces": total,
            "avg_duration_ms": round(float(stats_row.avg_duration_ms or 0), 1),
            "error_rate": round(error_count / total, 4) if total > 0 else 0.0,
            "total_input_tokens": int(stats_row.total_input_tokens or 0),
            "total_output_tokens": int(stats_row.total_output_tokens or 0),
        },
        "pagination": {"offset": offset, "limit": limit, "total": total},
    })


# ---------------------------------------------------------------------------
# Manifest Utilities
# ---------------------------------------------------------------------------


@router.get("/manifest/template", response_model=APIResponse[dict])
async def get_manifest_template() -> APIResponse[dict]:
    """Return a sample shipbridge.yaml template."""
    template = """version: "1"
name: "My Agent"
framework: custom
description: "Description of your AI agent"

models:
  - claude-3-5-sonnet
  - claude-3-haiku

tools:
  - name: search
    type: api
    endpoint: https://api.example.com/search
  - name: knowledge_base
    type: retrieval

connectors:
  - name: slack
    type: slack
    config:
      channel: "#alerts"

eval_cases:
  - input: "What is order status for #12345?"
    expected_output: "Order #12345 is in transit"
    category: order_status

policies:
  max_latency_ms: 3000
  max_cost_per_call: 0.05
  require_hitl:
    - refund_over_100
    - account_deletion

runtime:
  endpoint: https://agent.example.com/invoke
  health_check: https://agent.example.com/health
  auth_type: api_key
  auth_header: X-API-Key

deployment:
  target: railway
  auto_rollback: true
"""
    return APIResponse(data={"template": template, "format": "yaml"})


@router.post("/manifest/validate", response_model=APIResponse[dict])
async def validate_manifest_endpoint(
    body: ManifestValidateRequest,
) -> APIResponse[dict]:
    """Validate a shipbridge.yaml manifest without creating anything."""
    result = parse_manifest(body.yaml_content)
    return APIResponse(data=result.model_dump())
