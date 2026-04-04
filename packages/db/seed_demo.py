"""Seed script that creates demo data for local development.

Creates: demo tenant, demo user, demo project with sample stack_json,
sample assessment run with realistic scores, sample ingestion source (manifest mode),
sample runtime traces (10-20 traces with varying success/error),
sample HITL gate (one pending), sample audit log entries.

Usage:
    python -m packages.db.seed_demo
    # or from the repo root:
    python packages/db/seed_demo.py
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

# ──────────────────────────────────────────────
# Fixed IDs for repeatability
# ──────────────────────────────────────────────
DEMO_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DEMO_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


async def seed() -> None:
    """Populate the database with demo data."""
    # Import here so the script can be executed standalone
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db import _get_session_factory
    from app.models.auth import Tenant, User, Membership
    from app.models.projects import Project, AssessmentRun
    from app.models.ingestion import (
        IngestionSource,
        RuntimeTrace,
        AuditLogEntry,
        HITLGateRecord,
    )

    session_factory = _get_session_factory()

    async with session_factory() as db:
        db: AsyncSession

        # ── Tenant ──────────────────────────────────
        tenant = Tenant(
            id=DEMO_TENANT_ID,
            name="Demo Organization",
            slug="demo-org",
        )
        db.add(tenant)

        # ── User ────────────────────────────────────
        user = User(
            id=DEMO_USER_ID,
            tenant_id=DEMO_TENANT_ID,
            email="demo@shipbridge.dev",
            display_name="Demo User",
            password_hash="not-a-real-hash",
        )
        db.add(user)

        # ── Membership ──────────────────────────────
        membership = Membership(
            user_id=DEMO_USER_ID,
            tenant_id=DEMO_TENANT_ID,
            role="owner",
        )
        db.add(membership)

        # ── Project ─────────────────────────────────
        project = Project(
            id=DEMO_PROJECT_ID,
            tenant_id=DEMO_TENANT_ID,
            name="Customer Support Agent",
            framework="crewai",
            stack_json={
                "models": ["claude-3-5-sonnet", "claude-3-haiku"],
                "tools": [
                    {"name": "salesforce_lookup", "type": "api"},
                    {"name": "knowledge_base", "type": "retrieval"},
                ],
                "deployment": "railway",
                "auth": {"type": "api_key"},
                "injection_guard": True,
                "secrets_vault": True,
                "ci_grader": True,
                "test_coverage": 72,
                "eval_baseline": True,
                "eval_dataset": True,
                "audit_trail": True,
                "hitl_gates": True,
                "owner": "demo-user",
                "semantic_cache": False,
                "token_budget": True,
            },
            description="AI-powered customer support agent with Salesforce integration",
            repo_url="https://github.com/demo-org/support-agent",
        )
        db.add(project)

        # ── Assessment Run ──────────────────────────
        assessment = AssessmentRun(
            project_id=DEMO_PROJECT_ID,
            tenant_id=DEMO_TENANT_ID,
            total_score=76,
            scores_json={
                "reliability": {
                    "score": 85, "status": "ok",
                    "note": "Framework: crewai, 2 model(s), 2 tool(s)",
                    "issues": [{"title": "No deployment config", "evidence": "Missing deployment target", "fix_hint": "Set deployment to railway", "severity": "medium", "effort_days": 1}],
                },
                "security": {
                    "score": 80, "status": "ok",
                    "note": "1 security issue(s) detected",
                    "issues": [],
                },
                "eval": {
                    "score": 70, "status": "warn",
                    "note": "CI grader: yes, coverage: 72%",
                    "issues": [{"title": "Low test coverage", "evidence": "Test coverage at 72%", "fix_hint": "Increase test coverage to 80%+", "severity": "medium", "effort_days": 3}],
                },
                "governance": {
                    "score": 80, "status": "ok",
                    "note": "Audit: yes, HITL: yes",
                    "issues": [],
                },
                "cost": {
                    "score": 65, "status": "warn",
                    "note": "2 model(s), cache: no",
                    "issues": [{"title": "No semantic cache", "evidence": "Repeated queries hit the model every time", "fix_hint": "Add semantic cache with Redis", "severity": "medium", "effort_days": 2}],
                },
            },
            gap_report_json={
                "blockers": [
                    {"title": "No semantic cache", "evidence": "Repeated queries hit the model every time", "fix_hint": "Add semantic cache", "severity": "medium", "effort_days": 2},
                    {"title": "Low test coverage", "evidence": "72%", "fix_hint": "Increase to 80%+", "severity": "medium", "effort_days": 3},
                ],
                "total_issues": 2,
                "critical_count": 0,
                "estimated_effort_days": 5,
            },
            status="complete",
            triggered_by="seed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(assessment)

        # ── Ingestion Source (manifest) ─────────────
        ingestion = IngestionSource(
            project_id=DEMO_PROJECT_ID,
            tenant_id=DEMO_TENANT_ID,
            mode="manifest",
            config_json={
                "manifest_yaml": 'version: "1"\nname: "Customer Support Agent"\nframework: crewai\nmodels:\n  - claude-3-5-sonnet\n  - claude-3-haiku\n',
            },
            status="active",
            validation_result={"valid": True, "errors": [], "warnings": []},
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(ingestion)

        # ── Runtime Traces ──────────────────────────
        operations = ["llm_call", "tool_call", "retrieval", "classification", "summarization"]
        models = ["claude-3-5-sonnet", "claude-3-haiku", None]
        tool_names = ["salesforce_lookup", "knowledge_base", None, None]

        for i in range(15):
            status = "ok" if random.random() > 0.15 else "error"
            op = random.choice(operations)
            trace = RuntimeTrace(
                project_id=DEMO_PROJECT_ID,
                tenant_id=DEMO_TENANT_ID,
                trace_id=f"demo-trace-{uuid.uuid4().hex[:12]}",
                span_id=uuid.uuid4().hex[:16],
                parent_span_id=None if i == 0 else uuid.uuid4().hex[:16],
                operation=op,
                status=status,
                duration_ms=round(random.uniform(50, 4000), 1),
                input_tokens=random.randint(100, 2000),
                output_tokens=random.randint(50, 1000),
                model=random.choice(models),
                tool_name=random.choice(tool_names) if op == "tool_call" else None,
                error_message="Timeout connecting to external service" if status == "error" else None,
                metadata_json={"source": "seed"},
                started_at=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 72)),
            )
            db.add(trace)

        # ── HITL Gate (pending) ─────────────────────
        gate = HITLGateRecord(
            tenant_id=DEMO_TENANT_ID,
            title="Refund over $500 for order #98765",
            description="Customer requesting refund of $523.00 for damaged goods. Exceeds auto-approval threshold.",
            requested_by="support-agent",
            resource_type="refund",
            resource_id="order-98765",
            risk_level="high",
            status="pending",
            details_json={
                "amount": 523.00,
                "reason": "damaged_goods",
                "customer_tier": "premium",
            },
        )
        db.add(gate)

        # ── Audit Log Entries ───────────────────────
        audit_actions = [
            ("tool_call", "salesforce", "sf-query-123"),
            ("llm_decision", "classification", None),
            ("state_change", "ticket", "ticket-456"),
            ("hitl_request", "refund", "order-98765"),
            ("auth_event", "api_key", None),
            ("deployment_event", "deployment", "deploy-demo"),
        ]
        for action, resource_type, resource_id in audit_actions:
            entry = AuditLogEntry(
                tenant_id=DEMO_TENANT_ID,
                user_id=DEMO_USER_ID if action == "auth_event" else None,
                agent_id="support-agent" if action != "auth_event" else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details_json={"source": "seed", "action": action},
                ip_address="127.0.0.1",
            )
            db.add(entry)

        try:
            await db.commit()
            print("Demo data seeded successfully!")
            print(f"  Tenant:  {DEMO_TENANT_ID}")
            print(f"  User:    {DEMO_USER_ID} (demo@shipbridge.dev)")
            print(f"  Project: {DEMO_PROJECT_ID} (Customer Support Agent)")
            print(f"  Assessment score: 76")
            print(f"  Traces: 15")
            print(f"  HITL gates: 1 pending")
            print(f"  Audit entries: {len(audit_actions)}")
        except Exception as e:
            await db.rollback()
            print(f"Seed failed: {e}")
            print("Tables may not exist yet. Run migrations first.")


if __name__ == "__main__":
    asyncio.run(seed())
