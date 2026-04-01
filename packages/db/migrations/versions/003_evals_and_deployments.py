"""Create eval_runs, eval_baselines, deployment_stages tables.

Revision ID: 003
Revises: 002
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create eval and deployment stage tables."""
    # Enum
    eval_status = postgresql.ENUM("running", "complete", "failed", name="eval_status", create_type=False)
    eval_status.create(op.get_bind(), checkfirst=True)

    # eval_runs
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scores_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("baseline_delta", postgresql.JSON, nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("dataset_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pass_rate", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", eval_status, nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_project_id", "eval_runs", ["project_id"])
    op.create_index("ix_eval_runs_tenant_id", "eval_runs", ["tenant_id"])

    # eval_baselines
    op.create_table(
        "eval_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("eval_runs.id"), nullable=False),
        sa.Column("scores_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("dataset_snapshot", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_eval_baselines_project_id", "eval_baselines", ["project_id"])
    op.create_index("ix_eval_baselines_tenant_id", "eval_baselines", ["tenant_id"])

    # deployment_stages
    op.create_table(
        "deployment_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("deployment_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("traffic_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("metrics_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_deployment_stages_deployment_id", "deployment_stages", ["deployment_id"])
    op.create_index("ix_deployment_stages_tenant_id", "deployment_stages", ["tenant_id"])

    # RLS for all new tables
    for table in ("eval_runs", "eval_baselines", "deployment_stages"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
        """)


def downgrade() -> None:
    """Drop eval and deployment stage tables."""
    for table in ("deployment_stages", "eval_baselines", "eval_runs"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_table("deployment_stages")
    op.drop_table("eval_baselines")
    op.drop_table("eval_runs")
    op.execute("DROP TYPE IF EXISTS eval_status")
