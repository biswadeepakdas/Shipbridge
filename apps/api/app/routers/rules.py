import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis, from_url

from app.middleware.auth import AuthContext, get_auth_context
from app.os_layer.rule_registry import NormalizationRuleEntry, RuleRegistry
from app.os_layer.unknown_event_queue import unknown_event_queue
from app.schemas.response import APIResponse
from app.workers.rule_gen import (
    RuleGenerationResult,
    SchemaHash,
    check_schema_drift,
    list_drifted_schemas,
    run_rule_generator,
)
from app.config import get_settings

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])

class RuleListResponse(BaseModel):
    rules: list[NormalizationRuleEntry]
    unknown_queue_size: int

class PromoteRequest(BaseModel):
    app: str
    trigger: str

class SchemaCheckRequest(BaseModel):
    app: str
    trigger: str
    trigger_schema: dict

async def get_redis() -> Redis:
    settings = get_settings()
    return from_url(settings.redis_url, decode_responses=True)

@router.get("", response_model=APIResponse[RuleListResponse])
async def list_rules(
    app: str | None = None,
    auth: AuthContext = Depends(get_auth_context),
    redis: Redis = Depends(get_redis),
) -> APIResponse[RuleListResponse]:
    rule_registry = RuleRegistry(redis)
    rules = await rule_registry.list_rules(app)
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
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can trigger rule generation")

    result = await run_rule_generator() # Await the async function
    return APIResponse(data=result)

@router.post("/promote", response_model=APIResponse[dict])
async def promote_rule(
    body: PromoteRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: Redis = Depends(get_redis),
) -> APIResponse[dict]:
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can promote rules")

    rule_registry = RuleRegistry(redis)
    success = await rule_registry.promote(body.app, body.trigger)
    if not success:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.NOT_FOUND, f"No draft rule found for {body.app}:{body.trigger}")

    return APIResponse(data={"promoted": True, "app": body.app, "trigger": body.trigger})

@router.post("/archive", response_model=APIResponse[dict])
async def archive_rule(
    body: PromoteRequest,
    auth: AuthContext = Depends(get_auth_context),
    redis: Redis = Depends(get_redis),
) -> APIResponse[dict]:
    if auth.role not in ("admin", "owner"):
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.FORBIDDEN, "Only admins can archive rules")

    rule_registry = RuleRegistry(redis)
    success = await rule_registry.archive(body.app, body.trigger)
    if not success:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.NOT_FOUND, f"No rule found for {body.app}:{body.trigger}")

    return APIResponse(data={"archived": True, "app": body.app, "trigger": body.trigger})

@router.post("/schema-check", response_model=APIResponse[SchemaHash])
async def check_schema(
    body: SchemaCheckRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[SchemaHash]:
    result = check_schema_drift(body.app, body.trigger, body.trigger_schema)
    return APIResponse(data=result)

@router.get("/schema-drift", response_model=APIResponse[list[SchemaHash]])
async def get_drifted_schemas(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[SchemaHash]]:
    return APIResponse(data=list_drifted_schemas())
