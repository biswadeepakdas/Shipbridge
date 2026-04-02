"""Billing routes — plans, usage, upgrade, enforcement."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.exceptions import AppError, ErrorCode
from app.middleware.auth import AuthContext, get_auth_context
from app.schemas.response import APIResponse
from app.services.billing import (
    PLANS,
    BillingManager,
    EnforcementResult,
    PlanConfig,
    PlanTier,
    TenantBilling,
    billing_manager,
)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


class UpgradeRequest(BaseModel):
    plan: str  # "pro" or "enterprise"


class CheckLimitRequest(BaseModel):
    resource_type: str


@router.get("/plans", response_model=APIResponse[list[PlanConfig]])
async def list_plans() -> APIResponse[list[PlanConfig]]:
    """List all available billing plans."""
    return APIResponse(data=list(PLANS.values()))


@router.get("/current", response_model=APIResponse[TenantBilling])
async def get_current_billing(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[TenantBilling]:
    """Get current billing state for the authenticated tenant."""
    billing = billing_manager.get_billing(auth.tenant_id)
    return APIResponse(data=billing)


@router.post("/upgrade", response_model=APIResponse[TenantBilling])
async def upgrade_plan(
    body: UpgradeRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[TenantBilling]:
    """Upgrade to a new plan. In production, triggers Stripe Checkout."""
    try:
        plan = PlanTier(body.plan)
    except ValueError:
        raise AppError(ErrorCode.VALIDATION, f"Invalid plan: {body.plan}. Choose 'pro' or 'enterprise'.")

    if plan == PlanTier.FREE:
        raise AppError(ErrorCode.VALIDATION, "Cannot downgrade to Free via this endpoint")

    billing = billing_manager.upgrade(auth.tenant_id, plan)
    return APIResponse(data=billing)


@router.post("/check-limit", response_model=APIResponse[EnforcementResult])
async def check_limit(
    body: CheckLimitRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[EnforcementResult]:
    """Check if the tenant can create more of a resource type."""
    result = billing_manager.check_limit(auth.tenant_id, body.resource_type)
    return APIResponse(data=result)


@router.get("/usage", response_model=APIResponse[dict])
async def get_usage(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Get current usage metrics for the tenant."""
    billing = billing_manager.get_billing(auth.tenant_id)
    return APIResponse(data={
        "usage": billing.usage.model_dump(),
        "limits": {
            "projects": billing.limits.max_projects,
            "connectors": billing.limits.max_connectors,
            "assessments_per_month": billing.limits.max_assessments_per_month,
            "api_keys": billing.limits.max_api_keys,
        },
        "plan": billing.plan.value,
        "trial_active": billing.trial_active,
    })
