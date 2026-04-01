"""RuleRegistry — NormalizationRule lookup by (app, trigger) with in-memory cache.

In production, backed by Redis with 1h TTL and hot-reload on rule promotion.
"""

from datetime import datetime, timezone

from pydantic import BaseModel


class NormalizationRuleEntry(BaseModel):
    """A cached normalization rule entry."""

    rule_id: str
    app: str
    trigger: str
    payload_map: dict  # JMESPath expressions mapping raw → normalized fields
    status: str  # "draft", "active", "archived"
    version: int


class RuleRegistry:
    """In-memory normalization rule cache. Production uses Redis with 1h TTL."""

    def __init__(self) -> None:
        self._rules: dict[str, NormalizationRuleEntry] = {}

    def _cache_key(self, app: str, trigger: str) -> str:
        return f"{app}:{trigger}"

    def register(self, rule: NormalizationRuleEntry) -> None:
        """Register or update a rule in the cache."""
        key = self._cache_key(rule.app, rule.trigger)
        self._rules[key] = rule

    def lookup(self, app: str, trigger: str) -> NormalizationRuleEntry | None:
        """Lookup an active rule by (app, trigger). Returns None if not found."""
        key = self._cache_key(app, trigger)
        rule = self._rules.get(key)
        if rule and rule.status == "active":
            return rule
        return None

    def list_rules(self, app: str | None = None) -> list[NormalizationRuleEntry]:
        """List all rules, optionally filtered by app."""
        rules = list(self._rules.values())
        if app:
            rules = [r for r in rules if r.app == app]
        return rules

    def promote(self, app: str, trigger: str) -> bool:
        """Promote a draft rule to active status."""
        key = self._cache_key(app, trigger)
        rule = self._rules.get(key)
        if rule and rule.status == "draft":
            rule.status = "active"
            return True
        return False

    def archive(self, app: str, trigger: str) -> bool:
        """Archive an active rule."""
        key = self._cache_key(app, trigger)
        rule = self._rules.get(key)
        if rule:
            rule.status = "archived"
            return True
        return False

    def clear(self) -> None:
        """Clear all cached rules."""
        self._rules.clear()


# Singleton
rule_registry = RuleRegistry()
