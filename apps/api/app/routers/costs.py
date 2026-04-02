"""Cost modeling routes — projections, pricing, and optimization."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import Project
from app.schemas.response import APIResponse
from app.services.cost_modeler import (
    CostModelOutput,
    MODEL_PRICING,
    ModelPricing,
    TaskDistribution,
    TokenEstimate,
    project_costs,
)

router = APIRouter(prefix="/api/v1", tags=["costs"])


class CostProjectionRequest(BaseModel):
    """Optional overrides for cost projection."""

    monthly_tasks: int = 1000
    task_diversity: float = 0.6
    simple_pct: float = 0.50
    medium_pct: float = 0.35
    complex_pct: float = 0.15
    avg_input_tokens: int = 1500
    avg_output_tokens: int = 500


@router.post("/projects/{project_id}/cost-projection", response_model=APIResponse[CostModelOutput])
async def get_cost_projection(
    project_id: str,
    body: CostProjectionRequest = CostProjectionRequest(),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CostModelOutput]:
    """Generate cost projections at 1x, 10x, 100x scale for a project."""
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == uuid.UUID(auth.tenant_id),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise AppError(ErrorCode.NOT_FOUND, f"Project {project_id} not found")

    models = project.stack_json.get("models", [])
    has_cache = project.stack_json.get("semantic_cache", False)

    output = project_costs(
        models=models,
        monthly_tasks=body.monthly_tasks,
        distribution=TaskDistribution(
            simple_pct=body.simple_pct,
            medium_pct=body.medium_pct,
            complex_pct=body.complex_pct,
        ),
        tokens=TokenEstimate(
            avg_input_tokens=body.avg_input_tokens,
            avg_output_tokens=body.avg_output_tokens,
        ),
        has_cache=has_cache,
        task_diversity=body.task_diversity,
    )

    return APIResponse(data=output)


@router.get("/pricing", response_model=APIResponse[list[ModelPricing]])
async def list_model_pricing() -> APIResponse[list[ModelPricing]]:
    """List current model pricing table."""
    return APIResponse(data=list(MODEL_PRICING.values()))
