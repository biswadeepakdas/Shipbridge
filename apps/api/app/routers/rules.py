"""Normalization rule management routes — list, review, promote, run generator."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import AuthContext, get_auth_context
from app.os_layer.rule_registry import NormalizationRuleEntry, rule_registry
from app.os_layer.unknown_event_queue import unknown_event_queue
from app.schemas.response import APIResponse
from app.workers.rule_gen import (
    RuleGenerationResult,
    SchemaHash,
    check_schema_drift,
    list_drifted_schemas,
    run_rule_generator,
)

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


# --- Schemas ---

class RuleListResponse(BaseModel):
    """Rule list with queue stats."""

    rules: list[NormalizationRuleEntry]
    unknown_queue_size: int


class PromoteRequest(BaseModel):
    """Request to promote a draft rule."""

    app: str
    trigger: str


class SchemaCheckRequest(BaseModel):
    """Request to check schema drift."""

    app: str
    trigger: str
    trigger_schema: dict


# --- Routes ---

@router.get("", response_model=APIResponse[RuleListResponse])
async def list_rules(
    app: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[RuleListResponse]:
    """List all normalization rules with unknown queue stats."""
    rules = rule_registry.list_rules(app)
    return APIResponse(
        data=RuleListResponse(
            rules=rules,
            unknown_queue_size=unknown_event_queue.size,
        )
    )


@router.post("/generate", response_model=APIResponse[RuleGenerationResult])
async def trigger_rule_generation(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[RuleGenerationResult]:
    """Manually trigger the rule generator job. Drains unknown queue and generates drafts."""
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can trigger rule generation")

    result = run_rule_generator()
    return APIResponse(data=result)


@router.post("/promote", response_model=APIResponse[dict])
async def promote_rule(
    body: PromoteRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Promote a draft rule to active status."""
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can promote rules")

    success = rule_registry.promote(body.app, body.trigger)
    if not success:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.NOT_FOUND, f"No draft rule found for {body.app}:{body.trigger}")

    return APIResponse(data={"promoted": True, "app": body.app, "trigger": body.trigger})


@router.post("/archive", response_model=APIResponse[dict])
async def archive_rule(
    body: PromoteRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Archive an active rule."""
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can archive rules")

    success = rule_registry.archive(body.app, body.trigger)
    if not success:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.NOT_FOUND, f"No rule found for {body.app}:{body.trigger}")

    return APIResponse(data={"archived": True, "app": body.app, "trigger": body.trigger})


@router.post("/schema-check", response_model=APIResponse[SchemaHash])
async def check_schema(
    body: SchemaCheckRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[SchemaHash]:
    """Check a trigger schema for drift against stored hash."""
    result = check_schema_drift(body.app, body.trigger, body.trigger_schema)
    return APIResponse(data=result)


@router.get("/schema-drift", response_model=APIResponse[list[SchemaHash]])
async def get_drifted_schemas(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[SchemaHash]]:
    """List all schemas flagged for review due to drift."""
    return APIResponse(data=list_drifted_schemas())
