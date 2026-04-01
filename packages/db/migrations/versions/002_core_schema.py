"""Create core schema: projects, assessment_runs, connectors, events.

Revision ID: 002
Revises: 001
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create core domain tables."""
    # Enums
    for name, values in [
        ("agent_framework", ("langraph", "crewai", "autogen", "n8n", "custom")),
        ("assessment_status", ("running", "complete", "failed")),
        ("connector_auth_type", ("oauth2", "api_key", "basic", "none")),
        ("connector_status", ("healthy", "degraded", "down")),
        ("rule_status", ("draft", "active", "archived")),
    ]:
        enum = postgresql.ENUM(*values, name=name, create_type=False)
        enum.create(op.get_bind(), checkfirst=True)

    # Projects
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("framework", postgresql.ENUM("langraph", "crewai", "autogen", "n8n", "custom", name="agent_framework", create_type=False), nullable=False, server_default="custom"),
        sa.Column("stack_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("repo_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])

    # Assessment Runs
    op.create_table(
        "assessment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("scores_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("gap_report_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("status", postgresql.ENUM("running", "complete", "failed", name="assessment_status", create_type=False), nullable=False, server_default="running"),
        sa.Column("triggered_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assessment_runs_project_id", "assessment_runs", ["project_id"])
    op.create_index("ix_assessment_runs_tenant_id", "assessment_runs", ["tenant_id"])

    # Connectors
    op.create_table(
        "connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("adapter_type", sa.String(100), nullable=False),
        sa.Column("auth_type", postgresql.ENUM("oauth2", "api_key", "basic", "none", name="connector_auth_type", create_type=False), nullable=False, server_default="oauth2"),
        sa.Column("credentials_vault_ref", sa.String(500), nullable=True),
        sa.Column("config_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_connectors_tenant_id", "connectors", ["tenant_id"])

    # Connector Health
    op.create_table(
        "connector_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM("healthy", "degraded", "down", name="connector_status", create_type=False), nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_connector_health_connector_id", "connector_health", ["connector_id"])

    # Normalization Rules
    op.create_table(
        "normalization_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("app", sa.String(100), nullable=False),
        sa.Column("trigger", sa.String(255), nullable=False),
        sa.Column("payload_map", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("status", postgresql.ENUM("draft", "active", "archived", name="rule_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_normalization_rules_tenant_id", "normalization_rules", ["tenant_id"])
    op.create_index("ix_normalization_rules_app_trigger", "normalization_rules", ["app", "trigger"])

    # Agent Events
    op.create_table(
        "agent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("payload", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("dedup_key", sa.String(255), nullable=False),
        sa.Column("rule_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connectors.id"), nullable=True),
    )
    op.create_index("ix_agent_events_tenant_id", "agent_events", ["tenant_id"])
    op.create_index("ix_agent_events_event_type", "agent_events", ["event_type"])
    op.create_index("ix_agent_events_dedup_key", "agent_events", ["dedup_key"])

    # Event Subscriptions
    op.create_table(
        "event_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("filter_jmespath", sa.Text, nullable=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("debounce_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_event_subscriptions_tenant_id", "event_subscriptions", ["tenant_id"])
    op.create_index("ix_event_subscriptions_event_type", "event_subscriptions", ["event_type"])

    # Row Level Security — enforce tenant isolation at the database level
    # RLS policies use current_setting('app.current_tenant') set by the application
    # before each request via SET LOCAL app.current_tenant = '<tenant_uuid>';
    rls_tables = [
        "projects", "assessment_runs", "connectors",
        "connector_health", "normalization_rules",
        "agent_events", "event_subscriptions",
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
        """)


def downgrade() -> None:
    """Drop core domain tables."""
    # Remove RLS policies first
    rls_tables = [
        "event_subscriptions", "agent_events", "normalization_rules",
        "connector_health", "connectors", "assessment_runs", "projects",
    ]
    for table in rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("event_subscriptions")
    op.drop_table("agent_events")
    op.drop_table("normalization_rules")
    op.drop_table("connector_health")
    op.drop_table("connectors")
    op.drop_table("assessment_runs")
    op.drop_table("projects")
    for name in ("agent_framework", "assessment_status", "connector_auth_type", "connector_status", "rule_status"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
