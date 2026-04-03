"""Context assembly subsystem for RAG using pgvector and tsvector."""

import uuid
import hashlib
import json
import time
from typing import Any, List, Optional
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
import structlog

from app.models.projects import KnowledgeChunk
from app.config import get_settings
from openai import OpenAI

logger = structlog.get_logger()

# --- Intent Classification ---

class RetrievalIntent(str, Enum):
    """Classification of how to retrieve context for a query."""
    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    LIVE = "live"
    HYBRID = "hybrid"

class IntentClassification(BaseModel):
    """Result of intent classification."""
    intent: RetrievalIntent
    confidence: float
    reasoning: str

def classify_intent(query: str) -> IntentClassification:
    """Classify query intent to determine retrieval strategy."""
    lower = query.lower()
    structured_signals = ["how many", "count", "list all", "show me the", "get the", "what is the status of"]
    if any(s in lower for s in structured_signals):
        return IntentClassification(intent=RetrievalIntent.STRUCTURED, confidence=0.85, reasoning="Query contains structured lookup patterns")
    live_signals = ["right now", "current", "latest", "real-time", "live"]
    if any(s in lower for s in live_signals):
        return IntentClassification(intent=RetrievalIntent.LIVE, confidence=0.80, reasoning="Query requests real-time data")
    semantic_signals = ["explain", "why", "how does", "what are the", "compare", "summarize", "recommend"]
    if any(s in lower for s in semantic_signals):
        return IntentClassification(intent=RetrievalIntent.SEMANTIC, confidence=0.80, reasoning="Query requires conceptual understanding")
    return IntentClassification(intent=RetrievalIntent.HYBRID, confidence=0.60, reasoning="Ambiguous query — using hybrid retrieval for best coverage")

# --- Retrieval Models ---

class RetrievalChunk(BaseModel):
    """A single chunk returned from retrieval."""
    chunk_id: str
    content: str
    source: str
    score: float
    retrieval_method: str
    metadata: dict = {}

class RetrievalTrace(BaseModel):
    """Trace of the retrieval process for debugging."""
    intent: IntentClassification
    dense_results: int
    sparse_results: int
    fused_results: int
    cache_hit: bool
    retrieval_time_ms: float

class AssembledContext(BaseModel):
    """Final assembled context ready for agent consumption."""
    query: str
    chunks: List[RetrievalChunk]
    total_tokens_estimate: int
    retrieval_trace: RetrievalTrace
    assembled_at: str

# --- Production Context Assembly Subsystem ---

class ContextAssemblySubsystem:
    """
    Production-ready context assembly using:
    - pgvector for dense retrieval (semantic)
    - tsvector for sparse retrieval (keyword)
    - Redis for distributed caching
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.settings = get_settings()
        self.client = OpenAI()

    async def get_embeddings(self, text: str) -> List[float]:
        """Get embeddings from OpenAI."""
        response = self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    def _generate_cache_key(self, tenant_id: uuid.UUID, query: str, limit: int) -> str:
        """Generate a SHA-256 cache key."""
        payload = f"{tenant_id}:{query}:{limit}"
        return f"context:cache:{hashlib.sha256(payload.encode()).hexdigest()}"


    async def _write_audit_trail(self, tenant_id: str, project_id: str, query: str, chunks: list, model: str, tokens: dict):
        """Writes an audit trail entry to Redis."""
        import json
        from datetime import datetime
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "query": query,
            "retrieved_chunks": [c.id for c in chunks],
            "model_used": model,
            "tokens": tokens
        }
        key = f"audit:{tenant_id}:{project_id}"
        await self.redis.lpush(key, json.dumps(entry))
        await self.redis.ltrim(key, 0, 999)  # Keep last 1000 entries
    async def _dense_retrieval(
        self,
        tenant_id: uuid.UUID,
        query_embedding: List[float],
        project_id: Optional[uuid.UUID],
        limit: int,
    ) -> List[RetrievalChunk]:
        """Dense retrieval using pgvector cosine distance."""
        try:
            dense_stmt = (
                select(
                    KnowledgeChunk,
                    KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance"),
                )
                .where(KnowledgeChunk.tenant_id == tenant_id)
            )
            if project_id:
                dense_stmt = dense_stmt.where(KnowledgeChunk.project_id == project_id)

            dense_stmt = dense_stmt.order_by("distance").limit(limit)

            result = await self.db.execute(dense_stmt)
            chunks = []
            for row in result:
                chunk = row[0]
                chunks.append(RetrievalChunk(
                    chunk_id=str(chunk.id),
                    content=chunk.content,
                    source=chunk.source,
                    score=round(1 - row[1], 4),
                    retrieval_method="dense",
                    metadata=chunk.metadata_json,
                ))
            return chunks
        except Exception:
            logger.warning("dense_retrieval_failed", exc_info=True)
            return []

    async def _sparse_retrieval(
        self,
        tenant_id: uuid.UUID,
        query: str,
        project_id: Optional[uuid.UUID],
        limit: int,
    ) -> List[RetrievalChunk]:
        """Sparse retrieval using PostgreSQL tsvector full-text search."""
        try:
            ts_query = func.plainto_tsquery("english", query)
            sparse_stmt = (
                select(
                    KnowledgeChunk,
                    func.ts_rank(KnowledgeChunk.tsv_content, ts_query).label("rank"),
                )
                .where(
                    KnowledgeChunk.tenant_id == tenant_id,
                    KnowledgeChunk.tsv_content.op("@@")(ts_query),
                )
            )
            if project_id:
                sparse_stmt = sparse_stmt.where(KnowledgeChunk.project_id == project_id)

            sparse_stmt = sparse_stmt.order_by(text("rank DESC")).limit(limit)

            result = await self.db.execute(sparse_stmt)
            chunks = []
            for row in result:
                chunk = row[0]
                chunks.append(RetrievalChunk(
                    chunk_id=str(chunk.id),
                    content=chunk.content,
                    source=chunk.source,
                    score=round(float(row[1]), 4),
                    retrieval_method="sparse",
                    metadata=chunk.metadata_json,
                ))
            return chunks
        except Exception:
            logger.warning("sparse_retrieval_failed", exc_info=True)
            return []

    @staticmethod
    def _reciprocal_rank_fusion(
        dense: List[RetrievalChunk],
        sparse: List[RetrievalChunk],
        limit: int,
        k: int = 60,
    ) -> List[RetrievalChunk]:
        """Merge dense and sparse results using Reciprocal Rank Fusion (RRF).

        RRF score for a document = sum over lists of 1 / (k + rank).
        ``k`` is a smoothing constant (default 60, per the original paper).
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, RetrievalChunk] = {}

        for rank, chunk in enumerate(dense, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunk_map[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(sparse, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk.chunk_id not in chunk_map:
                chunk_map[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]

        fused: List[RetrievalChunk] = []
        for cid in sorted_ids:
            c = chunk_map[cid]
            fused.append(RetrievalChunk(
                chunk_id=c.chunk_id,
                content=c.content,
                source=c.source,
                score=round(scores[cid], 6),
                retrieval_method="hybrid",
                metadata=c.metadata,
            ))
        return fused

    async def assemble_context(
        self,
        tenant_id: uuid.UUID,
        query: str,
        project_id: Optional[uuid.UUID] = None,
        limit: int = 5
    ) -> AssembledContext:
        """
        Assemble context using hybrid search (pgvector + tsvector).
        """
        start_time = time.time()
        cache_key = self._generate_cache_key(tenant_id, query, limit)

        # 1. Check Redis Cache
        cached_data = await self.redis.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            trace = RetrievalTrace(
                intent=classify_intent(query),
                dense_results=0,
                sparse_results=0,
                fused_results=len(data),
                cache_hit=True,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
            return AssembledContext(
                query=query,
                chunks=[RetrievalChunk(**c) for c in data],
                total_tokens_estimate=len(cached_data) // 4,
                retrieval_trace=trace,
                assembled_at=datetime.now(timezone.utc).isoformat()
            )

        # 2. Classify intent and generate query embedding
        intent = classify_intent(query)
        query_embedding = await self.get_embeddings(query)

        # 3. Perform parallel dense (pgvector) and sparse (tsvector) retrieval
        # Fetch more candidates than needed so RRF has room to re-rank
        candidate_limit = limit * 2

        dense_chunks = await self._dense_retrieval(
            tenant_id, query_embedding, project_id, candidate_limit
        )
        sparse_chunks = await self._sparse_retrieval(
            tenant_id, query, project_id, candidate_limit
        )

        # 4. Fuse results with Reciprocal Rank Fusion
        if dense_chunks and sparse_chunks:
            chunks = self._reciprocal_rank_fusion(dense_chunks, sparse_chunks, limit)
        elif dense_chunks:
            chunks = dense_chunks[:limit]
        elif sparse_chunks:
            chunks = sparse_chunks[:limit]
        else:
            chunks = []

        # 5. Update Cache (24h TTL)
        chunks_data = [c.model_dump() for c in chunks]
        await self.redis.setex(
            cache_key,
            timedelta(hours=24),
            json.dumps(chunks_data)
        )

        trace = RetrievalTrace(
            intent=intent,
            dense_results=len(dense_chunks),
            sparse_results=len(sparse_chunks),
            fused_results=len(chunks),
            cache_hit=False,
            retrieval_time_ms=(time.time() - start_time) * 1000
        )

        return AssembledContext(
            query=query,
            chunks=chunks,
            total_tokens_estimate=sum(len(c.content) for c in chunks) // 4,
            retrieval_trace=trace,
            assembled_at=datetime.now(timezone.utc).isoformat()
        )

    async def ingest_knowledge(
        self,
        tenant_id: uuid.UUID,
        content: str,
        source: str,
        project_id: Optional[uuid.UUID] = None,
        metadata: Optional[dict] = None
    ) -> uuid.UUID:
        """Ingest a new knowledge chunk with embeddings and tsvector."""
        embedding = await self.get_embeddings(content)
        
        chunk = KnowledgeChunk(
            tenant_id=tenant_id,
            project_id=project_id,
            content=content,
            source=source,
            metadata_json=metadata or {},
            embedding=embedding,
            tsv_content=func.to_tsvector('english', content)
        )
        
        self.db.add(chunk)
        await self.db.commit()
        await self.db.refresh(chunk)
        return chunk.id
