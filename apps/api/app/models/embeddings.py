"""SQLAlchemy model for document embeddings with pgvector support."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.auth import utcnow


class DocumentEmbedding(Base):
    """Document chunk with vector embedding for retrieval.

    The actual pgvector VECTOR(1536) column is created via raw SQL in migration 004.
    embedding_text serves as a Text fallback for SQLite tests.
    """

    __tablename__ = "document_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
