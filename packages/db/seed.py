"""Database seeding script — loads dev fixtures for all core tables."""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# Add apps/api to path for model imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))


FIXTURES = {
    "tenants": [
        {
            "id": "a0000000-0000-0000-0000-000000000001",
            "name": "Acme AI Labs",
            "slug": "acme-ai",
        },
        {
            "id": "b0000000-0000-0000-0000-000000000002",
            "name": "Beta Corp",
            "slug": "beta-corp",
        },
    ],
    "users": [
        {
            "id": "u0000000-0000-0000-0000-000000000001",
            "email": "alice@acme.ai",
            "full_name": "Alice Engineer",
        },
        {
            "id": "u0000000-0000-0000-0000-000000000002",
            "email": "bob@beta.corp",
            "full_name": "Bob DevOps",
        },
    ],
    "memberships": [
        {
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "user_id": "u0000000-0000-0000-0000-000000000001",
            "role": "owner",
        },
        {
            "tenant_id": "b0000000-0000-0000-0000-000000000002",
            "user_id": "u0000000-0000-0000-0000-000000000002",
            "role": "owner",
        },
    ],
    "projects": [
        {
            "id": "p0000000-0000-0000-0000-000000000001",
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "name": "Customer Support Agent",
            "framework": "langraph",
            "stack_json": {
                "models": ["claude-3-5-sonnet", "claude-3-haiku"],
                "tools": ["salesforce", "zendesk"],
                "deployment": "railway",
            },
        },
        {
            "id": "p0000000-0000-0000-0000-000000000002",
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "name": "Code Review Bot",
            "framework": "crewai",
            "stack_json": {
                "models": ["claude-3-5-sonnet"],
                "tools": ["github", "linear"],
                "deployment": "vercel",
            },
        },
        {
            "id": "p0000000-0000-0000-0000-000000000003",
            "tenant_id": "b0000000-0000-0000-0000-000000000002",
            "name": "Data Pipeline Agent",
            "framework": "autogen",
            "stack_json": {
                "models": ["gpt-4o"],
                "tools": ["airtable", "postgres"],
                "deployment": "aws",
            },
        },
    ],
    "connectors": [
        {
            "id": "c0000000-0000-0000-0000-000000000001",
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "name": "Salesforce Production",
            "adapter_type": "salesforce",
            "auth_type": "oauth2",
        },
        {
            "id": "c0000000-0000-0000-0000-000000000002",
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "name": "Slack Workspace",
            "adapter_type": "slack",
            "auth_type": "oauth2",
        },
        {
            "id": "c0000000-0000-0000-0000-000000000003",
            "tenant_id": "b0000000-0000-0000-0000-000000000002",
            "name": "HubSpot",
            "adapter_type": "hubspot",
            "auth_type": "oauth2",
        },
    ],
    "normalization_rules": [
        {
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "app": "salesforce",
            "trigger": "opportunity_closed",
            "payload_map": {"event_type": "deal.closed", "amount": "payload.Amount"},
            "status": "active",
            "version": 1,
        },
        {
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "app": "slack",
            "trigger": "message_posted",
            "payload_map": {"event_type": "message.new", "text": "payload.text"},
            "status": "active",
            "version": 1,
        },
    ],
    "event_subscriptions": [
        {
            "tenant_id": "a0000000-0000-0000-0000-000000000001",
            "name": "New deal trigger",
            "event_type": "deal.closed",
            "filter_jmespath": "payload.amount > `10000`",
            "agent_id": "support-agent-v1",
            "debounce_seconds": 60,
        },
    ],
}


def print_fixtures() -> None:
    """Print fixture summary without requiring database."""
    total = sum(len(v) for v in FIXTURES.values())
    print(f"Seed fixtures ready: {total} records across {len(FIXTURES)} tables")
    for table, records in FIXTURES.items():
        print(f"  {table}: {len(records)} records")
    print("\nTo apply fixtures, run with a live database: make docker-up && make seed")


if __name__ == "__main__":
    print_fixtures()
