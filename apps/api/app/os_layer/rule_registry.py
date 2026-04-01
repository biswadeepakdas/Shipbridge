import json
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel
from redis.asyncio import Redis

class NormalizationRuleEntry(BaseModel):
    """A cached normalization rule entry."""
    rule_id: str
    app: str
    trigger: str
    payload_map: dict  # JMESPath expressions mapping raw → normalized fields
    status: str  # "draft", "active", "archived"
    version: int
    created_at: str = datetime.now(timezone.utc).isoformat()
    updated_at: str = datetime.now(timezone.utc).isoformat()

class RuleRegistry:
    """Redis-backed normalization rule cache with 1h TTL."""
    def __init__(self, redis: Redis):
        self.redis = redis
        self.rule_prefix = "rule:"
        self.rule_ttl = 3600  # 1 hour

    def _rule_key(self, app: str, trigger: str) -> str:
        return f"{self.rule_prefix}{app}:{trigger}"

    async def register(self, rule: NormalizationRuleEntry) -> None:
        """Register or update a rule in Redis."""
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        key = self._rule_key(rule.app, rule.trigger)
        await self.redis.set(key, rule.model_dump_json(), ex=self.rule_ttl)

    async def lookup(self, app: str, trigger: str) -> Optional[NormalizationRuleEntry]:
        """Lookup an active rule by (app, trigger) from Redis."""
        key = self._rule_key(app, trigger)
        rule_data = await self.redis.get(key)
        if rule_data:
            rule = NormalizationRuleEntry.model_validate_json(rule_data)
            if rule.status == "active":
                return rule
        return None

    async def list_rules(self, app: Optional[str] = None) -> List[NormalizationRuleEntry]:
        """List all rules, optionally filtered by app."""
        rules: List[NormalizationRuleEntry] = []
        async for key in self.redis.scan_iter(f"{self.rule_prefix}*"):
            rule_data = await self.redis.get(key)
            if rule_data:
                rule = NormalizationRuleEntry.model_validate_json(rule_data)
                if app is None or rule.app == app:
                    rules.append(rule)
        return rules

    async def promote(self, app: str, trigger: str) -> bool:
        """Promote a draft rule to active status in Redis."""
        key = self._rule_key(app, trigger)
        rule_data = await self.redis.get(key)
        if rule_data:
            rule = NormalizationRuleEntry.model_validate_json(rule_data)
            if rule.status == "draft":
                rule.status = "active"
                await self.register(rule) # Update in Redis
                return True
        return False

    async def archive(self, app: str, trigger: str) -> bool:
        """Archive an active rule in Redis."""
        key = self._rule_key(app, trigger)
        rule_data = await self.redis.get(key)
        if rule_data:
            rule = NormalizationRuleEntry.model_validate_json(rule_data)
            rule.status = "archived"
            await self.register(rule) # Update in Redis
            return True
        return False

    async def clear(self) -> None:
        """Clear all rules from Redis."""
        async for key in self.redis.scan_iter(f"{self.rule_prefix}*"):
            await self.redis.delete(key)

# The singleton will now be instantiated with a Redis client in the FastAPI app's lifespan event
# For now, we remove the global singleton to avoid issues with direct imports
# rule_registry = RuleRegistry()
