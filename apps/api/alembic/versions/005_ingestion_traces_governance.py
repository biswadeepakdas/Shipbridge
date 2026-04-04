"""Add ingestion_sources, runtime_traces, audit_log, and hitl_gates tables.

Revision ID: 005_ingestion
Revises: de96fdc811ae
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "005_ingestion"
down_revision = "de96fdc811ae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE ingestion_mode AS ENUM ('github_repo', 'runtime_endpoint', 'sdk_instrumentation', 'manifest')")
    op.execute("CREATE TYPE ingestion_status AS ENUM ('pending', 'validating', 'active', 'failed')")
    op.execute("CREATE TYPE trace_status AS ENUM ('ok', 'error')")
    op.execute("CREATE TYPE hitl_status AS ENUM ('pending', 'approved', 'rejected', 'expired')")

    # ingestion_sources
    op.create_table(
        "ingestion_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.Enum("github_repo", "runtime_endpoint", "sdk_instrumentation", "manifest", name="ingestion_mode", create_type=False), nullable=False),
        sa.Column("config_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.Enum("pending", "validating", "active", "failed", name="ingestion_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("validation_result", postgresql.JSON, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ingestion_sources_project_id", "ingestion_sources", ["project_id"])
    op.create_index("ix_ingestion_sources_tenant_id", "ingestion_sources", ["tenant_id"])

    # runtime_traces
    op.create_table(
        "runtime_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(255), nullable=False),
        sa.Column("span_id", sa.String(255), nullable=False),
        sa.Column("parent_span_id", sa.String(255), nullable=True),
        sa.Column("operation", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("ok", "error", name="trace_status", create_type=False), nullable=False, server_default="ok"),
        sa.Column("duration_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_runtime_traces_project_id", "runtime_traces", ["project_id"])
    op.create_index("ix_runtime_traces_tenant_id", "runtime_traces", ["tenant_id"])
    op.create_index("ix_runtime_traces_trace_id", "runtime_traces", ["trace_id"])

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("trace_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    # hitl_gates
    op.create_table(
        "hitl_gates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="high"),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", "expired", name="hitl_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("details_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_hitl_gates_tenant_id", "hitl_gates", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("hitl_gates")
    op.drop_table("audit_log")
    op.drop_table("runtime_traces")
    op.drop_table("ingestion_sources")
    op.execute("DROP TYPE IF EXISTS hitl_status")
    op.execute("DROP TYPE IF EXISTS trace_status")
    op.execute("DROP TYPE IF EXISTS ingestion_status")
    op.execute("DROP TYPE IF EXISTS ingestion_mode")
