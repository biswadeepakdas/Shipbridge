"""
Test All Frameworks — Serial assessment of 5 real-world agents through ShipBridge.
===================================================================================

Creates one project per framework, configures realistic stack_json, triggers
assessment, and prints results. Run against a live ShipBridge API.

Usage:
    python demo_agents/test_all_frameworks.py

Requires:
    SHIPBRIDGE_API_URL (default: http://localhost:8000)
    SHIPBRIDGE_TOKEN   (JWT token from /api/v1/auth/signup)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx

API_BASE = os.getenv("SHIPBRIDGE_API_URL", "http://localhost:8000")
TOKEN = os.getenv("SHIPBRIDGE_TOKEN", "")

# ─── Agent Configurations ────────────────────────────────────────────────────

AGENTS = [
    {
        "name": "LangGraph Customer Support Agent",
        "framework": "langraph",
        "description": "Multi-turn customer support agent with tool calling, memory, escalation logic, and Slack/Salesforce integration.",
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
        "description": "Multi-agent lead qualification crew with HITL review, HubSpot/Salesforce integration, and Slack notifications.",
        "repo_url": "https://github.com/crewAIInc/crewAI-examples/tree/main/lead-score-flow",
        "stack_json": {
            "models": ["claude-sonnet-4", "claude-haiku-4-5", "gpt-4o-mini"],
            "tools": ["hubspot_lead_fetch", "salesforce_crm_update", "slack_notification", "email_sender"],
            "deployment": "railway",
            "auth": {"type": "api_key", "provider": "custom"},
            "injection_guard": False,
            "user_input": True,
            "mcp_endpoints": [],
            "secrets_vault": True,
            "ci_grader": True,
            "test_coverage": 65,
            "eval_baseline": True,
            "eval_dataset": False,
            "audit_trail": True,
            "hitl_gates": True,
            "owner": "sales-ops@company.com",
            "compliance_docs": False,
            "semantic_cache": True,
            "token_budget": True,
        },
    },
    {
        "name": "AutoGen FastAPI Agent Chat",
        "framework": "autogen",
        "description": "Multi-agent conversation system deployed as FastAPI service with streaming handoffs and GitHub/Linear integration.",
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
            "secrets_vault": False,
            "ci_grader": False,
            "test_coverage": 45,
            "eval_baseline": False,
            "eval_dataset": False,
            "audit_trail": False,
            "hitl_gates": False,
            "owner": "dev-team@company.com",
            "compliance_docs": False,
            "semantic_cache": False,
            "token_budget": False,
        },
    },
    {
        "name": "n8n AI Workflow Starter",
        "framework": "n8n",
        "description": "Self-hosted AI workflows: Slack bot, document summarizer, appointment scheduler with 400+ n8n integrations.",
        "repo_url": "https://github.com/n8n-io/self-hosted-ai-starter-kit",
        "stack_json": {
            "models": ["llama-3.2", "claude-haiku-4-5"],
            "tools": ["slack_bot", "notion_reader", "google_calendar", "airtable_sync", "email_processor"],
            "deployment": "docker",
            "auth": {"type": "basic", "provider": "n8n"},
            "injection_guard": False,
            "user_input": True,
            "mcp_endpoints": [],
            "secrets_vault": False,
            "ci_grader": False,
            "test_coverage": 30,
            "eval_baseline": False,
            "eval_dataset": False,
            "audit_trail": True,
            "hitl_gates": False,
            "owner": "ops-team@company.com",
            "compliance_docs": False,
            "semantic_cache": False,
            "token_budget": False,
        },
    },
    {
        "name": "AutoGPT Autonomous Agent",
        "framework": "custom",
        "description": "Autonomous continuous agent platform — runs multi-step workflows for content creation, research, and data analysis.",
        "repo_url": "https://github.com/Significant-Gravitas/AutoGPT",
        "stack_json": {
            "models": ["gpt-4o"],
            "tools": ["web_browser", "file_manager", "code_executor", "search_engine"],
            "deployment": "docker",
            "auth": {},
            "injection_guard": False,
            "user_input": True,
            "mcp_endpoints": ["/tools/browser", "/tools/files", "/tools/code"],
            "mcp_auth": False,
            "secrets_vault": False,
            "ci_grader": False,
            "test_coverage": 20,
            "eval_baseline": False,
            "eval_dataset": False,
            "audit_trail": False,
            "hitl_gates": False,
            "owner": "",
            "compliance_docs": False,
            "semantic_cache": False,
            "token_budget": False,
        },
    },
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def headers():
    """Build request headers with auth token."""
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def print_divider():
    print("\n" + "=" * 80)


def print_pillar(name: str, data: dict):
    """Pretty-print a pillar score."""
    status_icon = {"ok": "✅", "warn": "⚠️", "bad": "❌"}.get(data.get("status", ""), "❓")
    print(f"  {status_icon} {name:15s}  {data['score']:3d}/100  ({data['status']})  — {data.get('note', '')}")
    for issue in data.get("issues", []):
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue.get("severity", ""), "⚪")
        print(f"       {sev_icon} {issue['title']}")
        print(f"         Fix: {issue['fix_hint']} ({issue['effort_days']}d)")


def signup_if_needed(client: httpx.Client) -> str:
    """Create a test account and return a JWT token."""
    resp = client.post(f"{API_BASE}/api/v1/auth/signup", json={
        "email": "demo@shipbridge.dev",
        "full_name": "Demo User",
        "tenant_name": "Demo Workspace",
        "tenant_slug": "demo-workspace",
    }, headers={"Content-Type": "application/json"})
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        return data.get("access_token", "")
    return ""


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    global TOKEN

    print("\n🚢 ShipBridge — Multi-Framework Agent Assessment")
    print(f"   API: {API_BASE}")
    print(f"   Time: {datetime.now(timezone.utc).isoformat()}")
    print_divider()

    client = httpx.Client(timeout=30.0)

    # Step 0: Health check
    try:
        health = client.get(f"{API_BASE}/health", timeout=5.0)
        if health.status_code != 200:
            print(f"\n❌ API health check failed ({health.status_code}). Is ShipBridge running at {API_BASE}?")
            print("   Set SHIPBRIDGE_API_URL to your Railway deployment URL.")
            return 1
    except Exception as e:
        print(f"\n❌ Cannot connect to API at {API_BASE}")
        print(f"   Error: {e}")
        print("\n   To run against your Railway deployment:")
        print("   SHIPBRIDGE_API_URL=https://your-app.railway.app python demo_agents/test_all_frameworks.py")
        return 1

    print("   ✅ API health check passed")

    # Step 0b: Auth
    if not TOKEN:
        print("\n🔑 No token provided. Signing up as demo user...")
        TOKEN = signup_if_needed(client)
        if TOKEN:
            print(f"   Token obtained: {TOKEN[:20]}...")
        else:
            print("   ⚠️  Could not obtain token. Running without auth.")

    results = []

    for i, agent in enumerate(AGENTS, 1):
        print_divider()
        print(f"\n🤖 Agent {i}/5: {agent['name']}")
        print(f"   Framework: {agent['framework']}")
        print(f"   Repo: {agent['repo_url']}")
        print(f"   Models: {', '.join(agent['stack_json']['models'])}")
        print(f"   Tools: {', '.join(agent['stack_json']['tools'])}")

        # Step 1: Create project
        print(f"\n   📦 Creating project...")
        resp = client.post(f"{API_BASE}/api/v1/projects", json={
            "name": agent["name"],
            "framework": agent["framework"],
            "stack_json": agent["stack_json"],
            "description": agent["description"],
            "repo_url": agent["repo_url"],
        }, headers=headers())

        if resp.status_code != 200:
            print(f"   ❌ Failed to create project: {resp.status_code} — {resp.text[:200]}")
            results.append({"name": agent["name"], "score": "FAILED", "status": "error"})
            continue

        project = resp.json().get("data", {})
        project_id = project.get("id", "")
        print(f"   ✅ Project created: {project_id}")

        # Step 2: Run assessment
        print(f"   🔍 Running 5-pillar assessment...")
        start = time.time()
        resp = client.post(f"{API_BASE}/api/v1/projects/{project_id}/assess", headers=headers())
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"   ❌ Assessment failed: {resp.status_code} — {resp.text[:200]}")
            results.append({"name": agent["name"], "score": "FAILED", "status": "error"})
            continue

        assessment = resp.json().get("data", {})
        total_score = assessment.get("total_score", 0)
        scores = assessment.get("scores_json", {})
        status = "PASS ✅" if total_score >= 75 else "FAIL ❌"

        print(f"\n   📊 Total Score: {total_score}/100 — {status}")
        print(f"   ⏱️  Assessment time: {elapsed:.2f}s\n")

        # Step 3: Print pillar breakdown
        pillar_order = ["reliability", "security", "eval", "governance", "cost"]
        for pillar in pillar_order:
            if pillar in scores:
                print_pillar(pillar.capitalize(), scores[pillar])

        # Step 4: Gap report summary
        gap_report = assessment.get("gap_report_json", {})
        ranked = gap_report.get("ranked_issues", [])
        total_days = gap_report.get("total_effort_days", 0)
        if ranked:
            print(f"\n   📋 Gap Report: {len(ranked)} issues, {total_days} days estimated effort")

        # Step 5: Readiness check
        print(f"\n   🚀 Checking readiness gate...")
        resp = client.get(f"{API_BASE}/api/v1/projects/{project_id}/readiness", headers=headers())
        if resp.status_code == 200:
            readiness = resp.json().get("data", {})
            can_deploy = readiness.get("can_deploy", False)
            gate_icon = "🟢" if can_deploy else "🔴"
            print(f"   {gate_icon} Deploy gate: {'OPEN — ready for staged deployment' if can_deploy else 'BLOCKED — address gap report first'}")
            print(f"      Score: {readiness.get('current_score', 0)}/{readiness.get('target_score', 75)} (gap: {readiness.get('gap', 0)})")

        results.append({
            "name": agent["name"],
            "framework": agent["framework"],
            "score": total_score,
            "status": "pass" if total_score >= 75 else "fail",
            "issues": len(ranked),
            "effort_days": total_days,
            "time_s": round(elapsed, 2),
        })

    # ─── Summary ─────────────────────────────────────────────────────────────
    print_divider()
    print("\n📊 ASSESSMENT SUMMARY")
    print_divider()
    print(f"\n  {'Agent':<40s} {'Framework':<12s} {'Score':>6s}  {'Status':>8s}  {'Issues':>7s}  {'Effort':>7s}")
    print(f"  {'─' * 40} {'─' * 12} {'─' * 6}  {'─' * 8}  {'─' * 7}  {'─' * 7}")
    for r in results:
        if isinstance(r.get("score"), int):
            icon = "✅" if r["status"] == "pass" else "❌"
            print(f"  {r['name']:<40s} {r['framework']:<12s} {r['score']:>5d}   {icon:>6s}    {r['issues']:>5d}    {r['effort_days']:>4d}d")
        else:
            print(f"  {r['name']:<40s} {'':12s} {'ERR':>6s}   {'💥':>6s}")

    passed = sum(1 for r in results if r.get("status") == "pass")
    print(f"\n  Result: {passed}/{len(results)} agents production-ready (score ≥ 75)")
    print_divider()

    return 0 if all(r.get("status") != "error" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
