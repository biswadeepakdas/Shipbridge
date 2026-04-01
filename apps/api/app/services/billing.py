"""Billing service — plans, usage metering, enforcement, trial management.

Plans: Free / Pro ($29) / Enterprise ($199)
Free tier: 1 project, 3 connectors, 5 assessments/month
Trial: 14 days Pro features on signup
"""

from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


class PlanTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PlanConfig(BaseModel):
    """Configuration for a billing plan."""

    tier: PlanTier
    name: str
    price_monthly: int  # cents
    max_projects: int
    max_connectors: int
    max_assessments_per_month: int
    max_api_keys: int
    staged_deployment: bool
    compliance_pdf: bool
    priority_support: bool


PLANS: dict[PlanTier, PlanConfig] = {
    PlanTier.FREE: PlanConfig(
        tier=PlanTier.FREE, name="Free", price_monthly=0,
        max_projects=1, max_connectors=3, max_assessments_per_month=5,
        max_api_keys=2, staged_deployment=False, compliance_pdf=False,
        priority_support=False,
    ),
    PlanTier.PRO: PlanConfig(
        tier=PlanTier.PRO, name="Pro", price_monthly=2900,
        max_projects=10, max_connectors=20, max_assessments_per_month=100,
        max_api_keys=10, staged_deployment=True, compliance_pdf=True,
        priority_support=False,
    ),
    PlanTier.ENTERPRISE: PlanConfig(
        tier=PlanTier.ENTERPRISE, name="Enterprise", price_monthly=19900,
        max_projects=999, max_connectors=999, max_assessments_per_month=9999,
        max_api_keys=50, staged_deployment=True, compliance_pdf=True,
        priority_support=True,
    ),
}


class UsageMetrics(BaseModel):
    """Current usage for a tenant."""

    projects: int = 0
    connectors: int = 0
    assessments_this_month: int = 0
    api_keys: int = 0


class TenantBilling(BaseModel):
    """Billing state for a tenant."""

    tenant_id: str
    plan: PlanTier
    trial_active: bool = False
    trial_ends_at: str | None = None
    usage: UsageMetrics
    limits: PlanConfig
    can_upgrade: bool = True


class EnforcementResult(BaseModel):
    """Result of a plan enforcement check."""

    allowed: bool
    resource_type: str
    current_count: int
    limit: int
    message: str


class BillingManager:
    """Manages tenant billing state, usage, and enforcement."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantBilling] = {}

    def initialize_tenant(self, tenant_id: str) -> TenantBilling:
        """Initialize billing for a new tenant with Free plan + 14-day Pro trial."""
        trial_end = datetime.now(timezone.utc) + timedelta(days=14)
        billing = TenantBilling(
            tenant_id=tenant_id,
            plan=PlanTier.FREE,
            trial_active=True,
            trial_ends_at=trial_end.isoformat(),
            usage=UsageMetrics(),
            limits=PLANS[PlanTier.PRO],  # Trial gets Pro limits
        )
        self._tenants[tenant_id] = billing
        logger.info("billing_initialized", tenant_id=tenant_id, trial_ends=trial_end.isoformat())
        return billing

    def get_billing(self, tenant_id: str) -> TenantBilling:
        """Get or initialize billing for a tenant."""
        if tenant_id not in self._tenants:
            return self.initialize_tenant(tenant_id)

        billing = self._tenants[tenant_id]

        # Check trial expiry
        if billing.trial_active and billing.trial_ends_at:
            trial_end = datetime.fromisoformat(billing.trial_ends_at)
            if trial_end < datetime.now(timezone.utc):
                billing.trial_active = False
                billing.limits = PLANS[billing.plan]
                logger.info("trial_expired", tenant_id=tenant_id)

        return billing

    def upgrade(self, tenant_id: str, new_plan: PlanTier) -> TenantBilling:
        """Upgrade a tenant's plan."""
        billing = self.get_billing(tenant_id)
        billing.plan = new_plan
        billing.trial_active = False
        billing.limits = PLANS[new_plan]
        logger.info("plan_upgraded", tenant_id=tenant_id, plan=new_plan.value)
        return billing

    def record_usage(self, tenant_id: str, resource_type: str, delta: int = 1) -> None:
        """Record usage increment for a resource type."""
        billing = self.get_billing(tenant_id)
        if resource_type == "project":
            billing.usage.projects += delta
        elif resource_type == "connector":
            billing.usage.connectors += delta
        elif resource_type == "assessment":
            billing.usage.assessments_this_month += delta
        elif resource_type == "api_key":
            billing.usage.api_keys += delta

    def check_limit(self, tenant_id: str, resource_type: str) -> EnforcementResult:
        """Check if a tenant can create more of a resource type."""
        billing = self.get_billing(tenant_id)
        usage = billing.usage
        limits = billing.limits

        checks = {
            "project": (usage.projects, limits.max_projects),
            "connector": (usage.connectors, limits.max_connectors),
            "assessment": (usage.assessments_this_month, limits.max_assessments_per_month),
            "api_key": (usage.api_keys, limits.max_api_keys),
        }

        current, limit = checks.get(resource_type, (0, 999))
        allowed = current < limit

        message = f"OK — {current}/{limit} {resource_type}s used" if allowed else \
            f"Limit reached: {current}/{limit} {resource_type}s. Upgrade to {self._next_plan(billing.plan).value} for more."

        return EnforcementResult(
            allowed=allowed, resource_type=resource_type,
            current_count=current, limit=limit, message=message,
        )

    def check_feature(self, tenant_id: str, feature: str) -> bool:
        """Check if a feature is available on the tenant's plan."""
        billing = self.get_billing(tenant_id)
        features = {
            "staged_deployment": billing.limits.staged_deployment,
            "compliance_pdf": billing.limits.compliance_pdf,
            "priority_support": billing.limits.priority_support,
        }
        return features.get(feature, False)

    @staticmethod
    def _next_plan(current: PlanTier) -> PlanTier:
        if current == PlanTier.FREE:
            return PlanTier.PRO
        return PlanTier.ENTERPRISE

    def clear(self) -> None:
        self._tenants.clear()


# Singleton
billing_manager = BillingManager()
