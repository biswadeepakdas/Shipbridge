"""SQLAlchemy models for projects and assessment runs."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, Index
from sqlalchemy.dialects.postgresql import JSON, UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

class Project(Base):
    """A project represents an AI agent system being evaluated."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    framework: Mapped[str] = mapped_column(
        Enum("langraph", "crewai", "autogen", "n8n", "custom", name="agent_framework"),
        nullable=False,
        default="custom",
    )
    stack_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    assessment_runs: Mapped[list["AssessmentRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class AssessmentRun(Base):
    """A single assessment run scoring a project across 5 pillars."""

    __tablename__ = "assessment_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scores_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    gap_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        Enum("running", "complete", "failed", name="assessment_status"),
        nullable=False,
        default="running",
    )
    triggered_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="assessment_runs")


class KnowledgeChunk(Base):
    """A chunk of knowledge for RAG, stored in pgvector."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=False)
    tsv_content: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_knowledge_chunks_tsv", "tsv_content", postgresql_using="gin"),
    )

# SLA and budget fields added by strategic implementation

    # SLA enforcement fields (Agent 1 — Reliability)
    sla_max_latency_ms = Column(Float, nullable=True)
    sla_max_cost_per_call = Column(Float, nullable=True)
    sla_max_hallucination_rate = Column(Float, nullable=True)
    # Budget cap (Agent 3 — Enterprise Trust)
    monthly_budget_limit = Column(Float, nullable=True, default=None)
