"""Create document_embeddings table with pgvector.

Revision ID: 004
Revises: 003
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document_embeddings with pgvector column and GIN index."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "document_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.String(255), nullable=False, unique=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("metadata_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Add pgvector column
    op.execute("ALTER TABLE document_embeddings ADD COLUMN embedding vector(1536);")

    # Indexes
    op.create_index("ix_document_embeddings_tenant_id", "document_embeddings", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_document_embeddings_embedding "
        "ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )

    # tsvector for sparse/full-text search
    op.execute(
        "ALTER TABLE document_embeddings "
        "ADD COLUMN content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;"
    )
    op.execute("CREATE INDEX ix_document_embeddings_content_tsv ON document_embeddings USING GIN (content_tsv);")

    # RLS
    op.execute("ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON document_embeddings
        USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    """Drop document_embeddings table."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON document_embeddings;")
    op.drop_table("document_embeddings")
