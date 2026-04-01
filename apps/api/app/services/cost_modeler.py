"""Cost + Token Modeler — pricing, routing optimization, scale projections, cache estimation."""

from pydantic import BaseModel


# --- Model Pricing (per 1M tokens, updated monthly) ---

class ModelPricing(BaseModel):
    """Pricing for a single model tier."""

    model: str
    input_per_1m: float  # USD per 1M input tokens
    output_per_1m: float  # USD per 1M output tokens
    tier: str  # "fast", "balanced", "powerful"


# Current pricing as of March 2026
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-3-haiku": ModelPricing(model="claude-3-haiku", input_per_1m=0.25, output_per_1m=1.25, tier="fast"),
    "claude-3-5-haiku": ModelPricing(model="claude-3-5-haiku", input_per_1m=0.80, output_per_1m=4.00, tier="fast"),
    "claude-3-5-sonnet": ModelPricing(model="claude-3-5-sonnet", input_per_1m=3.00, output_per_1m=15.00, tier="balanced"),
    "claude-sonnet-4": ModelPricing(model="claude-sonnet-4", input_per_1m=3.00, output_per_1m=15.00, tier="balanced"),
    "claude-opus-4": ModelPricing(model="claude-opus-4", input_per_1m=15.00, output_per_1m=75.00, tier="powerful"),
    "gpt-4o": ModelPricing(model="gpt-4o", input_per_1m=2.50, output_per_1m=10.00, tier="balanced"),
    "gpt-4o-mini": ModelPricing(model="gpt-4o-mini", input_per_1m=0.15, output_per_1m=0.60, tier="fast"),
}

# Default fallback pricing for unknown models
DEFAULT_PRICING = ModelPricing(model="unknown", input_per_1m=3.00, output_per_1m=15.00, tier="balanced")


# --- Schemas ---

class TaskDistribution(BaseModel):
    """Distribution of task complexity across the three tiers."""

    simple_pct: float = 0.50  # routed to fast tier
    medium_pct: float = 0.35  # routed to balanced tier
    complex_pct: float = 0.15  # routed to powerful tier


class TokenEstimate(BaseModel):
    """Token usage estimate per task."""

    avg_input_tokens: int = 1500
    avg_output_tokens: int = 500


class CostProjection(BaseModel):
    """Cost projection for a specific scale scenario."""

    scale_label: str  # "1x", "10x", "100x"
    monthly_tasks: int
    models_used: list[str]
    cost_per_model: dict[str, float]
    total_monthly_cost: float
    cost_per_task: float
    cache_savings: float
    effective_cost: float  # after cache savings


class CacheEstimate(BaseModel):
    """Semantic cache hit rate estimation."""

    estimated_hit_rate: float  # 0.0 to 1.0
    unique_task_ratio: float
    monthly_cache_savings: float
    reasoning: str


class CostModelOutput(BaseModel):
    """Complete cost model output."""

    models: list[ModelPricing]
    task_distribution: TaskDistribution
    projections: list[CostProjection]  # 1x, 10x, 100x
    cache_estimate: CacheEstimate
    routing_recommendation: str
    monthly_baseline: float


# --- 3-Tier Routing Optimizer ---

def classify_model_tier(model: str) -> str:
    """Classify a model into its cost tier."""
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return pricing.tier


def get_optimal_routing(models: list[str]) -> dict[str, str]:
    """Map task complexity to the cheapest capable model.

    Returns: {"simple": model_name, "medium": model_name, "complex": model_name}
    """
    # Separate models by tier
    by_tier: dict[str, list[str]] = {"fast": [], "balanced": [], "powerful": []}
    for model in models:
        tier = classify_model_tier(model)
        by_tier[tier].append(model)

    # Pick cheapest per tier, fall back to available models
    routing: dict[str, str] = {}

    # Simple tasks → fast tier (cheapest)
    if by_tier["fast"]:
        routing["simple"] = min(by_tier["fast"], key=lambda m: MODEL_PRICING.get(m, DEFAULT_PRICING).input_per_1m)
    elif by_tier["balanced"]:
        routing["simple"] = by_tier["balanced"][0]
    elif models:
        routing["simple"] = models[0]

    # Medium tasks → balanced tier
    if by_tier["balanced"]:
        routing["medium"] = by_tier["balanced"][0]
    elif by_tier["fast"]:
        routing["medium"] = by_tier["fast"][0]
    elif models:
        routing["medium"] = models[0]

    # Complex tasks → powerful tier
    if by_tier["powerful"]:
        routing["complex"] = by_tier["powerful"][0]
    elif by_tier["balanced"]:
        routing["complex"] = by_tier["balanced"][0]
    elif models:
        routing["complex"] = models[0]

    return routing


# --- Semantic Cache Estimator ---

def estimate_cache_hit_rate(
    monthly_tasks: int,
    task_diversity: float = 0.6,  # 0.0 = all identical, 1.0 = all unique
    has_cache: bool = False,
) -> CacheEstimate:
    """Estimate semantic cache hit rate from task diversity score.

    Higher diversity = lower hit rate. No cache = 0% savings.
    """
    if not has_cache:
        return CacheEstimate(
            estimated_hit_rate=0.0,
            unique_task_ratio=task_diversity,
            monthly_cache_savings=0.0,
            reasoning="No semantic cache configured. Add Redis-based cache to reduce redundant LLM calls.",
        )

    # Hit rate inversely proportional to diversity
    # Low diversity (0.2) → 50% hit rate, High diversity (0.8) → 15% hit rate
    hit_rate = max(0.05, min(0.50, 0.60 - (task_diversity * 0.55)))

    return CacheEstimate(
        estimated_hit_rate=round(hit_rate, 3),
        unique_task_ratio=task_diversity,
        monthly_cache_savings=0.0,  # filled in by projection
        reasoning=f"Estimated {hit_rate:.0%} cache hit rate based on {task_diversity:.0%} task diversity.",
    )


# --- Cost Projector ---

def project_costs(
    models: list[str],
    monthly_tasks: int,
    distribution: TaskDistribution | None = None,
    tokens: TokenEstimate | None = None,
    has_cache: bool = False,
    task_diversity: float = 0.6,
) -> CostModelOutput:
    """Generate cost projections at 1x, 10x, and 100x scale."""
    if distribution is None:
        distribution = TaskDistribution()
    if tokens is None:
        tokens = TokenEstimate()

    routing = get_optimal_routing(models)
    model_pricing_list = [MODEL_PRICING.get(m, DEFAULT_PRICING) for m in models]

    projections: list[CostProjection] = []
    scales = [("1x", 1), ("10x", 10), ("100x", 100)]

    for label, multiplier in scales:
        tasks = monthly_tasks * multiplier
        cost_per_model: dict[str, float] = {}

        # Calculate cost for each complexity tier
        tier_tasks = {
            "simple": int(tasks * distribution.simple_pct),
            "medium": int(tasks * distribution.medium_pct),
            "complex": int(tasks * distribution.complex_pct),
        }

        total_cost = 0.0
        for tier, tier_count in tier_tasks.items():
            model = routing.get(tier, models[0] if models else "unknown")
            pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

            input_cost = (tier_count * tokens.avg_input_tokens / 1_000_000) * pricing.input_per_1m
            output_cost = (tier_count * tokens.avg_output_tokens / 1_000_000) * pricing.output_per_1m
            model_cost = input_cost + output_cost

            cost_per_model[model] = cost_per_model.get(model, 0) + model_cost
            total_cost += model_cost

        # Cache savings
        cache = estimate_cache_hit_rate(tasks, task_diversity, has_cache)
        cache_savings = total_cost * cache.estimated_hit_rate
        effective = total_cost - cache_savings

        projections.append(CostProjection(
            scale_label=label,
            monthly_tasks=tasks,
            models_used=list(cost_per_model.keys()),
            cost_per_model={k: round(v, 2) for k, v in cost_per_model.items()},
            total_monthly_cost=round(total_cost, 2),
            cost_per_task=round(total_cost / max(tasks, 1), 4),
            cache_savings=round(cache_savings, 2),
            effective_cost=round(effective, 2),
        ))

    # Generate routing recommendation
    if len(models) >= 3:
        rec = "3-tier routing active. Optimal cost structure."
    elif len(models) == 2:
        rec = "2-tier routing. Add a fast-tier model (e.g., Haiku) for simple tasks to reduce cost by ~30%."
    else:
        rec = "Single model — no routing. Implement 3-tier routing to reduce cost by up to 60%."

    cache_est = estimate_cache_hit_rate(monthly_tasks, task_diversity, has_cache)
    if has_cache and projections:
        cache_est.monthly_cache_savings = projections[0].cache_savings

    return CostModelOutput(
        models=model_pricing_list,
        task_distribution=distribution,
        projections=projections,
        cache_estimate=cache_est,
        routing_recommendation=rec,
        monthly_baseline=projections[0].effective_cost if projections else 0.0,
    )


# ─── Budget Caps, Spend Tracking & Intelligent Model Routing ─────────────────

MODEL_PRICING = {
    "gpt-4o":           {"prompt": 0.005,    "completion": 0.015},
    "gpt-4o-mini":      {"prompt": 0.00015,  "completion": 0.0006},
    "gemini-2.5-flash": {"prompt": 0.000075, "completion": 0.0003},
}


class CostModeler:
    """Tracks real-time spend, enforces budget caps, and routes to cost-optimal models."""

    async def record_usage(self, redis_client, tenant_id: str, project_id: str,
                           prompt_tokens: int, completion_tokens: int, model: str):
        """Records token usage and increments spend counters in Redis."""
        from datetime import datetime
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])
        cost = (prompt_tokens / 1000 * pricing["prompt"]) + (completion_tokens / 1000 * pricing["completion"])
        now = datetime.utcnow()
        month_key = f"spend:{tenant_id}:{project_id}:{now.strftime('%Y-%m')}"
        day_key   = f"spend:{tenant_id}:{project_id}:{now.strftime('%Y-%m-%d')}"
        await redis_client.incrbyfloat(month_key, cost)
        await redis_client.incrbyfloat(day_key, cost)
        return cost

    async def check_budget(self, redis_client, tenant_id: str, project_id: str,
                           monthly_limit: float) -> bool:
        """Returns False if the monthly budget has been exceeded, True otherwise."""
        from datetime import datetime
        month_key = f"spend:{tenant_id}:{project_id}:{datetime.utcnow().strftime('%Y-%m')}"
        current = await redis_client.get(month_key)
        if current is None:
            return True
        return float(current) < monthly_limit

    async def get_spend_summary(self, redis_client, tenant_id: str, project_id: str) -> dict:
        """Returns current month spend, daily breakdown, and projected end-of-month spend."""
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        month_key = f"spend:{tenant_id}:{project_id}:{now.strftime('%Y-%m')}"
        current_raw = await redis_client.get(month_key)
        current_month = float(current_raw) if current_raw else 0.0

        daily = {}
        for i in range(7):
            day = now - timedelta(days=i)
            day_key = f"spend:{tenant_id}:{project_id}:{day.strftime('%Y-%m-%d')}"
            val = await redis_client.get(day_key)
            daily[day.strftime("%Y-%m-%d")] = float(val) if val else 0.0

        days_elapsed = now.day
        projected = (current_month / days_elapsed * 30) if days_elapsed > 0 else 0.0

        return {
            "current_month_spend": round(current_month, 6),
            "daily_breakdown": daily,
            "projected_month_end": round(projected, 6),
        }

    def select_model(self, prompt: str, budget_remaining: float) -> str:
        """Selects the most cost-effective model based on prompt complexity and remaining budget."""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model("gpt-4o")
            token_count = len(enc.encode(prompt))
        except Exception:
            token_count = int(len(prompt.split()) * 1.3)

        if budget_remaining < 0.10:
            return "gemini-2.5-flash"
        if token_count >= 500 and budget_remaining > 1.00:
            return "gpt-4o"
        return "gpt-4o-mini"
