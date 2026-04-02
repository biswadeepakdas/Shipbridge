"""Tests for core domain models — CRUD operations and cross-tenant isolation."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Membership, Tenant, User
from app.models.connectors import Connector, ConnectorHealth, NormalizationRule
from app.models.events import AgentEvent, EventSubscription
from app.models.projects import AssessmentRun, Project


async def _create_tenant(db: AsyncSession, name: str, slug: str) -> Tenant:
    """Helper to create a tenant."""
    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    await db.flush()
    return tenant


async def _create_project(db: AsyncSession, tenant_id: uuid.UUID, name: str) -> Project:
    """Helper to create a project."""
    project = Project(
        tenant_id=tenant_id,
        name=name,
        framework="langraph",
        stack_json={"models": ["claude-3-5-sonnet"]},
    )
    db.add(project)
    await db.flush()
    return project


@pytest.mark.asyncio
async def test_create_project(db_session: AsyncSession) -> None:
    """Can create a project linked to a tenant."""
    tenant = await _create_tenant(db_session, "Test Corp", "test-corp")
    project = await _create_project(db_session, tenant.id, "My Agent")
    await db_session.commit()

    result = await db_session.execute(select(Project).where(Project.id == project.id))
    fetched = result.scalar_one()
    assert fetched.name == "My Agent"
    assert fetched.framework == "langraph"
    assert fetched.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_create_assessment_run(db_session: AsyncSession) -> None:
    """Can create an assessment run with scores and gap report."""
    tenant = await _create_tenant(db_session, "Assess Corp", "assess-corp")
    project = await _create_project(db_session, tenant.id, "Agent X")

    run = AssessmentRun(
        project_id=project.id,
        tenant_id=tenant.id,
        total_score=72,
        scores_json={
            "reliability": {"score": 80, "status": "ok"},
            "security": {"score": 60, "status": "warn"},
            "eval": {"score": 75, "status": "ok"},
            "governance": {"score": 70, "status": "warn"},
            "cost": {"score": 75, "status": "ok"},
        },
        gap_report_json={
            "blockers": [
                {"title": "No prompt injection guard", "severity": "high", "effort_days": 2}
            ]
        },
        status="complete",
    )
    db_session.add(run)
    await db_session.commit()

    result = await db_session.execute(select(AssessmentRun).where(AssessmentRun.id == run.id))
    fetched = result.scalar_one()
    assert fetched.total_score == 72
    assert fetched.status == "complete"
    assert len(fetched.gap_report_json["blockers"]) == 1


@pytest.mark.asyncio
async def test_create_connector_with_health(db_session: AsyncSession) -> None:
    """Can create a connector and attach health check records."""
    tenant = await _create_tenant(db_session, "Connect Corp", "connect-corp")
    connector = Connector(
        tenant_id=tenant.id,
        name="Salesforce Prod",
        adapter_type="salesforce",
        auth_type="oauth2",
    )
    db_session.add(connector)
    await db_session.flush()

    health = ConnectorHealth(
        connector_id=connector.id,
        status="healthy",
        latency_ms=45.2,
    )
    db_session.add(health)
    await db_session.commit()

    result = await db_session.execute(
        select(ConnectorHealth).where(ConnectorHealth.connector_id == connector.id)
    )
    fetched = result.scalar_one()
    assert fetched.status == "healthy"
    assert fetched.latency_ms == 45.2


@pytest.mark.asyncio
async def test_create_normalization_rule(db_session: AsyncSession) -> None:
    """Can create a normalization rule with payload map."""
    tenant = await _create_tenant(db_session, "Rule Corp", "rule-corp")
    rule = NormalizationRule(
        tenant_id=tenant.id,
        app="salesforce",
        trigger="opportunity_closed",
        payload_map={"event_type": "deal.closed", "amount": "payload.Amount"},
        status="active",
        version=1,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(
        select(NormalizationRule).where(NormalizationRule.tenant_id == tenant.id)
    )
    fetched = result.scalar_one()
    assert fetched.app == "salesforce"
    assert fetched.payload_map["event_type"] == "deal.closed"


@pytest.mark.asyncio
async def test_create_agent_event(db_session: AsyncSession) -> None:
    """Can create an agent event with dedup key."""
    tenant = await _create_tenant(db_session, "Event Corp", "event-corp")
    event = AgentEvent(
        tenant_id=tenant.id,
        source="salesforce",
        event_type="deal.closed",
        occurred_at=datetime.now(timezone.utc),
        payload={"deal_id": "123", "amount": 50000},
        dedup_key="sf-opp-123-closed",
        rule_version=1,
    )
    db_session.add(event)
    await db_session.commit()

    result = await db_session.execute(
        select(AgentEvent).where(AgentEvent.dedup_key == "sf-opp-123-closed")
    )
    fetched = result.scalar_one()
    assert fetched.event_type == "deal.closed"
    assert fetched.payload["amount"] == 50000


@pytest.mark.asyncio
async def test_create_event_subscription(db_session: AsyncSession) -> None:
    """Can create an event subscription with JMESPath filter."""
    tenant = await _create_tenant(db_session, "Sub Corp", "sub-corp")
    sub = EventSubscription(
        tenant_id=tenant.id,
        name="High value deals",
        event_type="deal.closed",
        filter_jmespath="payload.amount > `10000`",
        agent_id="support-agent-v1",
        debounce_seconds=60,
    )
    db_session.add(sub)
    await db_session.commit()

    result = await db_session.execute(
        select(EventSubscription).where(EventSubscription.tenant_id == tenant.id)
    )
    fetched = result.scalar_one()
    assert fetched.agent_id == "support-agent-v1"
    assert fetched.debounce_seconds == 60


@pytest.mark.asyncio
async def test_cross_tenant_project_isolation(db_session: AsyncSession) -> None:
    """Tenant A's projects are not visible when querying by tenant B's ID."""
    tenant_a = await _create_tenant(db_session, "A Corp", "a-corp-iso")
    tenant_b = await _create_tenant(db_session, "B Corp", "b-corp-iso")

    await _create_project(db_session, tenant_a.id, "Agent A")
    await _create_project(db_session, tenant_b.id, "Agent B")
    await db_session.commit()

    # Query as tenant B — should only see tenant B's project
    result = await db_session.execute(
        select(Project).where(Project.tenant_id == tenant_b.id)
    )
    projects = result.scalars().all()
    assert len(projects) == 1
    assert projects[0].name == "Agent B"


@pytest.mark.asyncio
async def test_cross_tenant_connector_isolation(db_session: AsyncSession) -> None:
    """Tenant A's connectors are not visible when querying by tenant B's ID."""
    tenant_a = await _create_tenant(db_session, "A Conn", "a-conn-iso")
    tenant_b = await _create_tenant(db_session, "B Conn", "b-conn-iso")

    db_session.add(Connector(tenant_id=tenant_a.id, name="SF A", adapter_type="salesforce", auth_type="oauth2"))
    db_session.add(Connector(tenant_id=tenant_b.id, name="SF B", adapter_type="salesforce", auth_type="oauth2"))
    await db_session.commit()

    result = await db_session.execute(
        select(Connector).where(Connector.tenant_id == tenant_b.id)
    )
    connectors = result.scalars().all()
    assert len(connectors) == 1
    assert connectors[0].name == "SF B"


@pytest.mark.asyncio
async def test_cross_tenant_event_isolation(db_session: AsyncSession) -> None:
    """Tenant A's events are not visible when querying by tenant B's ID."""
    tenant_a = await _create_tenant(db_session, "A Evt", "a-evt-iso")
    tenant_b = await _create_tenant(db_session, "B Evt", "b-evt-iso")

    db_session.add(AgentEvent(
        tenant_id=tenant_a.id, source="slack", event_type="message.new",
        occurred_at=datetime.now(timezone.utc), payload={}, dedup_key="evt-a-1",
    ))
    db_session.add(AgentEvent(
        tenant_id=tenant_b.id, source="slack", event_type="message.new",
        occurred_at=datetime.now(timezone.utc), payload={}, dedup_key="evt-b-1",
    ))
    await db_session.commit()

    result = await db_session.execute(
        select(AgentEvent).where(AgentEvent.tenant_id == tenant_b.id)
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].dedup_key == "evt-b-1"
