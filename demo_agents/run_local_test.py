"""
Run Local Test — Execute 5-agent assessment in-process without external services.
==================================================================================

Uses SQLite in-memory DB + ASGI transport (no network, no Postgres, no Redis needed).
Skips models that require pgvector/tsvector by patching the metadata.

Usage:
    cd apps/api && python -m demo_agents.run_local_test
    OR
    python demo_agents/run_local_test.py
"""

import asyncio
import json
import os
import sys
import time

# Set environment BEFORE importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_SECRET"] = "test-secret-for-demo"
os.environ["ENVIRONMENT"] = "development"

# Add apps/api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event, text


# ─── Agent Configurations ────────────────────────────────────────────────────

AGENTS = [
    {
        "name": "LangGraph Customer Support Agent",
        "framework": "langraph",
        "description": "Multi-turn customer support with tool calling, memory, and escalation.",
        "repo_url": "https://github.com/langchain-ai/langgraph/tree/main/examples/customer-support",
        "stack_json": {
            "models": ["claude-sonnet-4", "claude-haiku-4-5"],
            "tools": ["salesforce_crm_lookup", "stripe_billing_query", "slack_notify", "knowledge_base_search"],
            "deployment": "railway",
            "auth": {"type": "jwt", "provider": "supabase"},
            "injection_guard": True,
            "user_input": True,
            "mcp_endpoints": ["/tools/salesforce", "/tools/stripe"],
            "mcp_auth": True,
            "secrets_vault": True,
            "ci_grader": True,
            "test_coverage": 78,
            "eval_baseline": True,
            "eval_dataset": True,
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "support-team@company.com",
            "compliance_docs": True,
            "semantic_cache": True,
            "token_budget": True,
        },
    },
    {
        "name": "CrewAI Lead Score Flow",
        "framework": "crewai",
        "description": "Lead qualification crew with HITL review and CRM integration.",
        "repo_url": "https://github.com/crewAIInc/crewAI-examples/tree/main/lead-score-flow",
        "stack_json": {
            "models": ["claude-sonnet-4", "claude-haiku-4-5", "gpt-4o-mini"],
            "tools": ["hubspot_lead_fetch", "salesforce_crm_update", "slack_notification", "email_sender"],
            "deployment": "railway",
            "auth": {"type": "api_key", "provider": "custom"},
            "injection_guard": False,
            "user_input": True,
            "secrets_vault": True,
            "ci_grader": True,
            "test_coverage": 65,
            "eval_baseline": True,
            "eval_dataset": False,
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "sales-ops@company.com",
            "semantic_cache": True,
            "token_budget": True,
        },
    },
    {
        "name": "AutoGen FastAPI Agent Chat",
        "framework": "autogen",
        "description": "Multi-agent conversation system with streaming handoffs.",
        "repo_url": "https://github.com/microsoft/autogen/tree/main/python/samples/agentchat_fastapi",
        "stack_json": {
            "models": ["gpt-4o", "gpt-4o-mini"],
            "tools": ["github_code_search", "linear_issue_tracker", "code_executor"],
            "deployment": "railway",
            "auth": {"type": "oauth2", "provider": "github"},
            "injection_guard": True,
            "user_input": True,
            "mcp_endpoints": ["/tools/github", "/tools/linear"],
            "mcp_auth": True,
            "ci_grader": False,
            "test_coverage": 45,
            "audit_trail": False,
            "hitl_gates": False,
            "owner": "dev-team@company.com",
        },
    },
    {
        "name": "n8n AI Workflow Starter",
        "framework": "n8n",
        "description": "Self-hosted AI workflows: Slack bot, doc summarizer, scheduler.",
        "repo_url": "https://github.com/n8n-io/self-hosted-ai-starter-kit",
        "stack_json": {
            "models": ["llama-3.2", "claude-haiku-4-5"],
            "tools": ["slack_bot", "notion_reader", "google_calendar", "airtable_sync", "email_processor"],
            "deployment": "docker",
            "auth": {"type": "basic", "provider": "n8n"},
            "user_input": True,
            "test_coverage": 30,
            "audit_trail": True,
            "owner": "ops-team@company.com",
        },
    },
    {
        "name": "AutoGPT Autonomous Agent",
        "framework": "custom",
        "description": "Autonomous continuous agent for content, research, and data analysis.",
        "repo_url": "https://github.com/Significant-Gravitas/AutoGPT",
        "stack_json": {
            "models": ["gpt-4o"],
            "tools": ["web_browser", "file_manager", "code_executor", "search_engine"],
            "deployment": "docker",
            "user_input": True,
            "mcp_endpoints": ["/tools/browser", "/tools/files", "/tools/code"],
            "test_coverage": 20,
        },
    },
]


# ─── Setup ───────────────────────────────────────────────────────────────────

async def setup_app():
    """Set up in-memory SQLite DB and configure the app."""
    from app.db import Base, get_db
    from app.main import app as fastapi_app

    # Create in-memory engine that skips problematic column types
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # Import models
    import app.models  # noqa: F401

    # Filter out tables with unsupported column types (TSVECTOR, pgvector)
    tables_to_create = []
    for table in Base.metadata.sorted_tables:
        skip = False
        for col in table.columns:
            type_name = str(col.type).upper()
            if "TSVECTOR" in type_name or "VECTOR" in type_name:
                skip = True
                break
        if not skip:
            tables_to_create.append(table)

    async with test_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create))

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_db

    # Reset rate limiter
    from app.middleware.rate_limit import rate_limiter
    rate_limiter.reset()

    return fastapi_app, test_engine


# ─── Helpers ─────────────────────────────────────────────────────────────────

def print_divider():
    print("\n" + "=" * 80)


def print_pillar(name: str, data: dict):
    status_icon = {"ok": "✅", "warn": "⚠️ ", "bad": "❌"}.get(data.get("status", ""), "❓")
    print(f"  {status_icon} {name:15s}  {data['score']:3d}/100  ({data['status']})  — {data.get('note', '')}")
    for issue in data.get("issues", []):
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue.get("severity", ""), "⚪")
        print(f"       {sev_icon} {issue['title']}")
        print(f"         Fix: {issue['fix_hint']} ({issue['effort_days']}d)")


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    from httpx import ASGITransport, AsyncClient

    print("\n🚢 ShipBridge — Multi-Framework Agent Assessment (Local)")
    print(f"   Database: SQLite in-memory")
    print(f"   Mode: ASGI in-process (no network)")
    print_divider()

    # Setup
    print("\n⚙️  Setting up in-memory database...")
    app, engine = await setup_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        resp = await client.get("/health")
        print(f"   ✅ Health check: {resp.status_code}")

        # Sign up
        print("\n🔑 Creating demo user...")
        resp = await client.post("/api/v1/auth/signup", json={
            "email": "demo@shipbridge.dev",
            "full_name": "Demo User",
            "tenant_name": "Demo Workspace",
            "tenant_slug": "demo-workspace",
        })
        auth_data = resp.json().get("data", {})
        token_data = auth_data.get("token", auth_data)
        token = token_data.get("access_token", auth_data.get("access_token", ""))
        tenant = auth_data.get("tenant", {"name": "Demo"})
        if token:
            print(f"   ✅ Signed up. Tenant: {tenant.get('name', 'unknown')}")
        else:
            print(f"   ❌ Signup failed: {resp.text[:200]}")
            return 1

        headers = {"Authorization": f"Bearer {token}"}
        results = []

        for i, agent in enumerate(AGENTS, 1):
            print_divider()
            print(f"\n🤖 Agent {i}/5: {agent['name']}")
            print(f"   Framework: {agent['framework']}")
            print(f"   Models: {', '.join(agent['stack_json']['models'])}")
            print(f"   Tools: {', '.join(agent['stack_json']['tools'])}")

            # Create project
            print(f"\n   📦 Creating project...")
            resp = await client.post("/api/v1/projects", json={
                "name": agent["name"],
                "framework": agent["framework"],
                "stack_json": agent["stack_json"],
                "description": agent["description"],
                "repo_url": agent["repo_url"],
            }, headers=headers)

            if resp.status_code != 200:
                print(f"   ❌ Failed: {resp.status_code} — {resp.text[:200]}")
                results.append({"name": agent["name"], "score": "ERR", "status": "error"})
                continue

            project = resp.json().get("data", {})
            project_id = project.get("id", "")
            print(f"   ✅ Project: {project_id}")

            # Run assessment
            print(f"   🔍 Running 5-pillar assessment...")
            start = time.time()
            resp = await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
            elapsed = time.time() - start

            if resp.status_code != 200:
                print(f"   ❌ Assessment failed: {resp.status_code} — {resp.text[:200]}")
                results.append({"name": agent["name"], "score": "ERR", "status": "error"})
                continue

            assessment = resp.json().get("data", {})
            total_score = assessment.get("total_score", 0)
            scores = assessment.get("scores_json", {})
            gap_report = assessment.get("gap_report_json", {})
            ranked = gap_report.get("ranked_issues", [])
            total_days = gap_report.get("total_effort_days", 0)
            passed = total_score >= 75

            print(f"\n   📊 Total Score: {total_score}/100 — {'PASS ✅' if passed else 'FAIL ❌'}")
            print(f"   ⏱️  Time: {elapsed:.2f}s\n")

            for pillar in ["reliability", "security", "eval", "governance", "cost"]:
                if pillar in scores:
                    print_pillar(pillar.capitalize(), scores[pillar])

            if ranked:
                print(f"\n   📋 Gap Report: {len(ranked)} issues, {total_days}d effort")

            # Readiness gate
            resp = await client.get(f"/api/v1/projects/{project_id}/readiness", headers=headers)
            if resp.status_code == 200:
                readiness = resp.json().get("data", {})
                can_deploy = readiness.get("can_deploy", False)
                gate = "🟢 OPEN" if can_deploy else "🔴 BLOCKED"
                print(f"\n   🚀 Deploy gate: {gate} ({readiness.get('current_score', 0)}/{readiness.get('target_score', 75)})")

            results.append({
                "name": agent["name"],
                "framework": agent["framework"],
                "score": total_score,
                "status": "pass" if passed else "fail",
                "issues": len(ranked),
                "effort_days": total_days,
                "time_s": round(elapsed, 2),
            })

    # Summary
    print_divider()
    print("\n📊 ASSESSMENT SUMMARY")
    print_divider()
    print(f"\n  {'Agent':<40s} {'Framework':<12s} {'Score':>6s}  {'Gate':>6s}  {'Issues':>7s}  {'Effort':>7s}")
    print(f"  {'─' * 40} {'─' * 12} {'─' * 6}  {'─' * 6}  {'─' * 7}  {'─' * 7}")
    for r in results:
        if isinstance(r.get("score"), int):
            icon = "✅" if r["status"] == "pass" else "❌"
            print(f"  {r['name']:<40s} {r['framework']:<12s} {r['score']:>5d}   {icon:>4s}    {r['issues']:>5d}    {r['effort_days']:>4d}d")
        else:
            print(f"  {r['name']:<40s} {'':12s} {'ERR':>6s}   {'💥':>4s}")

    passed_count = sum(1 for r in results if r.get("status") == "pass")
    total = len(results)
    print(f"\n  🏁 Result: {passed_count}/{total} agents production-ready (score ≥ 75)")
    print_divider()

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: None)  # no-op cleanup
    await engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
