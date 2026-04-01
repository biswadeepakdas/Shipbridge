"""ContextAssemblyEngine — intent classifier → hybrid retrieval → context cache.

Assembles relevant context for agent consumption by combining:
1. Intent classification (structured / semantic / live / hybrid)
2. Dense retrieval (pgvector cosine similarity)
3. Sparse retrieval (BM25-style keyword matching)
4. Reciprocal rank fusion to merge result sets
5. SHA-256 context cache with 24h TTL
"""

import hashlib
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel

import structlog

logger = structlog.get_logger()


# --- Intent Classification ---

class RetrievalIntent(str, Enum):
    """Classification of how to retrieve context for a query."""

    STRUCTURED = "structured"  # Direct DB lookup (SQL-like)
    SEMANTIC = "semantic"      # Vector similarity search
    LIVE = "live"              # Real-time connector fetch
    HYBRID = "hybrid"          # Combine dense + sparse retrieval


class IntentClassification(BaseModel):
    """Result of intent classification."""

    intent: RetrievalIntent
    confidence: float
    reasoning: str


def classify_intent(query: str) -> IntentClassification:
    """Classify query intent to determine retrieval strategy.

    In production, calls Haiku (~50ms) for classification.
    Uses heuristic rules for development.
    """
    lower = query.lower()

    # Structured: explicit data lookups
    structured_signals = ["how many", "count", "list all", "show me the", "get the", "what is the status of"]
    if any(s in lower for s in structured_signals):
        return IntentClassification(
            intent=RetrievalIntent.STRUCTURED, confidence=0.85,
            reasoning="Query contains structured lookup patterns",
        )

    # Live: real-time data needs
    live_signals = ["right now", "current", "latest", "real-time", "live"]
    if any(s in lower for s in live_signals):
        return IntentClassification(
            intent=RetrievalIntent.LIVE, confidence=0.80,
            reasoning="Query requests real-time data",
        )

    # Semantic: conceptual/knowledge questions
    semantic_signals = ["explain", "why", "how does", "what are the", "compare", "summarize", "recommend"]
    if any(s in lower for s in semantic_signals):
        return IntentClassification(
            intent=RetrievalIntent.SEMANTIC, confidence=0.80,
            reasoning="Query requires conceptual understanding",
        )

    # Default: hybrid
    return IntentClassification(
        intent=RetrievalIntent.HYBRID, confidence=0.60,
        reasoning="Ambiguous query — using hybrid retrieval for best coverage",
    )


# --- Retrieval Chunks ---

class RetrievalChunk(BaseModel):
    """A single chunk returned from retrieval."""

    chunk_id: str
    content: str
    source: str
    score: float
    retrieval_method: str  # "dense", "sparse", "fused"
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
    chunks: list[RetrievalChunk]
    total_tokens_estimate: int
    retrieval_trace: RetrievalTrace
    assembled_at: str


# --- Dense Retrieval (pgvector simulation) ---

def dense_retrieval(query: str, tenant_id: str, top_k: int = 10) -> list[RetrievalChunk]:
    """Simulate pgvector cosine similarity search.

    In production: embed query → SELECT with <=> operator on tenant-namespaced vectors.
    """
    # Simulated results based on query keywords
    words = set(query.lower().split())
    simulated_docs = [
        {"id": "d1", "content": "The agent uses multi-model routing with Haiku for simple tasks and Sonnet for complex reasoning.", "source": "docs/architecture.md", "keywords": {"agent", "model", "routing", "haiku", "sonnet"}},
        {"id": "d2", "content": "Circuit breakers protect against cascading failures. After 5 consecutive failures, the circuit opens for 30 seconds.", "source": "docs/resilience.md", "keywords": {"circuit", "breaker", "failure", "resilience"}},
        {"id": "d3", "content": "The assessment engine scores projects across 5 pillars: reliability, security, eval, governance, and cost.", "source": "docs/assessment.md", "keywords": {"assessment", "score", "pillar", "reliability", "security"}},
        {"id": "d4", "content": "Connectors normalize external data into agent-friendly markdown format using JMESPath payload maps.", "source": "docs/connectors.md", "keywords": {"connector", "normalize", "data", "jmespath", "payload"}},
        {"id": "d5", "content": "Deployment follows a staged pipeline: sandbox → canary 5% → canary 25% → production with auto-rollback.", "source": "docs/deployment.md", "keywords": {"deployment", "canary", "production", "rollback", "staged"}},
        {"id": "d6", "content": "The eval harness generates test suites with LLM-as-judge graders and CI gate templates.", "source": "docs/eval.md", "keywords": {"eval", "test", "grader", "ci", "harness"}},
        {"id": "d7", "content": "HITL gates require human approval before high-risk agent actions proceed.", "source": "docs/governance.md", "keywords": {"hitl", "human", "approval", "governance", "gate"}},
        {"id": "d8", "content": "Semantic cache reduces redundant LLM calls by caching responses for similar queries.", "source": "docs/cost.md", "keywords": {"cache", "semantic", "cost", "token", "llm"}},
    ]

    scored = []
    for doc in simulated_docs:
        overlap = len(words & doc["keywords"])
        if overlap > 0:
            score = min(0.95, 0.3 + overlap * 0.15)
            scored.append(RetrievalChunk(
                chunk_id=doc["id"], content=doc["content"], source=doc["source"],
                score=round(score, 3), retrieval_method="dense", metadata={"overlap": overlap},
            ))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


# --- Sparse Retrieval (BM25-style) ---

def sparse_retrieval(query: str, tenant_id: str, top_k: int = 10) -> list[RetrievalChunk]:
    """Simulate BM25-style sparse retrieval using tsvector/GIN index.

    In production: uses PostgreSQL ts_rank with GIN index on content column.
    """
    words = set(query.lower().split())
    simulated_docs = [
        {"id": "s1", "content": "Production readiness requires a score of 75 or higher across all assessment pillars.", "source": "docs/readiness.md", "keywords": {"production", "readiness", "score", "assessment"}},
        {"id": "s2", "content": "API keys are HMAC-hashed before storage. Never store raw API keys in the database.", "source": "docs/security.md", "keywords": {"api", "key", "hmac", "security", "storage"}},
        {"id": "s3", "content": "Webhooks are verified using HMAC-SHA256 signatures before processing.", "source": "docs/webhooks.md", "keywords": {"webhook", "hmac", "signature", "verify"}},
        {"id": "s4", "content": "The cost modeler projects expenses at 1x, 10x, and 100x scale with per-model breakdown.", "source": "docs/cost-model.md", "keywords": {"cost", "model", "scale", "projection", "expense"}},
        {"id": "s5", "content": "Tenant isolation is enforced via RLS policies and tenant_id on every database query.", "source": "docs/multi-tenancy.md", "keywords": {"tenant", "isolation", "rls", "multi-tenancy"}},
    ]

    scored = []
    for doc in simulated_docs:
        overlap = len(words & doc["keywords"])
        if overlap > 0:
            score = min(0.90, 0.25 + overlap * 0.18)
            scored.append(RetrievalChunk(
                chunk_id=doc["id"], content=doc["content"], source=doc["source"],
                score=round(score, 3), retrieval_method="sparse", metadata={"keyword_hits": overlap},
            ))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


# --- Reciprocal Rank Fusion ---

def reciprocal_rank_fusion(
    dense_results: list[RetrievalChunk],
    sparse_results: list[RetrievalChunk],
    k: int = 60,
) -> list[RetrievalChunk]:
    """Merge dense + sparse result sets using reciprocal rank fusion.

    RRF score = sum(1 / (k + rank)) for each result list the chunk appears in.
    """
    scores: dict[str, float] = {}
    chunk_map: dict[str, RetrievalChunk] = {}

    for rank, chunk in enumerate(dense_results):
        rrf = 1.0 / (k + rank + 1)
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + rrf
        chunk_map[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(sparse_results):
        rrf = 1.0 / (k + rank + 1)
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + rrf
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk

    # Sort by fused score
    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    fused = []
    for cid in sorted_ids:
        chunk = chunk_map[cid]
        fused.append(RetrievalChunk(
            chunk_id=chunk.chunk_id, content=chunk.content, source=chunk.source,
            score=round(scores[cid], 5), retrieval_method="fused",
            metadata={**chunk.metadata, "rrf_score": round(scores[cid], 5)},
        ))

    return fused


# --- Context Cache (SHA-256, 24h TTL) ---

class ContextCache:
    """In-memory context cache. Production uses Redis with 24h TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[AssembledContext, float]] = {}
        self._ttl_seconds = 86400  # 24h
        self._hits = 0
        self._misses = 0

    def _cache_key(self, query: str, tenant_id: str) -> str:
        raw = f"{tenant_id}:{query}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, query: str, tenant_id: str) -> AssembledContext | None:
        key = self._cache_key(query, tenant_id)
        entry = self._store.get(key)
        if entry:
            ctx, stored_at = entry
            if (time.time() - stored_at) < self._ttl_seconds:
                self._hits += 1
                return ctx
            del self._store[key]
        self._misses += 1
        return None

    def put(self, query: str, tenant_id: str, context: AssembledContext) -> None:
        key = self._cache_key(query, tenant_id)
        self._store[key] = (context, time.time())

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "hit_rate": round(self.hit_rate, 3), "size": len(self._store)}


# Singleton
context_cache = ContextCache()


# --- Main Context Assembly ---

def assemble_context(
    query: str,
    tenant_id: str,
    top_k: int = 5,
    use_cache: bool = True,
) -> AssembledContext:
    """Full context assembly pipeline: intent → hybrid retrieval → cache."""
    start = time.monotonic()

    # Check cache
    if use_cache:
        cached = context_cache.get(query, tenant_id)
        if cached:
            logger.info("context_cache_hit", query=query[:50], tenant_id=tenant_id)
            # Return copy with cache_hit flag set
            trace = cached.retrieval_trace.model_copy(update={"cache_hit": True})
            return cached.model_copy(update={"retrieval_trace": trace})

    # Classify intent
    intent = classify_intent(query)

    # Retrieve based on intent
    dense_results: list[RetrievalChunk] = []
    sparse_results: list[RetrievalChunk] = []

    if intent.intent in (RetrievalIntent.SEMANTIC, RetrievalIntent.HYBRID):
        dense_results = dense_retrieval(query, tenant_id, top_k=top_k * 2)

    if intent.intent in (RetrievalIntent.STRUCTURED, RetrievalIntent.HYBRID):
        sparse_results = sparse_retrieval(query, tenant_id, top_k=top_k * 2)

    if intent.intent == RetrievalIntent.LIVE:
        # For live queries, use sparse as a fallback
        sparse_results = sparse_retrieval(query, tenant_id, top_k=top_k)

    # Fuse results
    if dense_results and sparse_results:
        chunks = reciprocal_rank_fusion(dense_results, sparse_results)[:top_k]
    elif dense_results:
        chunks = dense_results[:top_k]
    elif sparse_results:
        chunks = sparse_results[:top_k]
    else:
        chunks = []

    # Estimate tokens (rough: 1 token ≈ 4 chars)
    total_chars = sum(len(c.content) for c in chunks)
    token_estimate = total_chars // 4

    duration_ms = (time.monotonic() - start) * 1000

    trace = RetrievalTrace(
        intent=intent,
        dense_results=len(dense_results),
        sparse_results=len(sparse_results),
        fused_results=len(chunks),
        cache_hit=False,
        retrieval_time_ms=round(duration_ms, 2),
    )

    context = AssembledContext(
        query=query,
        chunks=chunks,
        total_tokens_estimate=token_estimate,
        retrieval_trace=trace,
        assembled_at=datetime.now(timezone.utc).isoformat(),
    )

    # Cache the result
    if use_cache:
        context_cache.put(query, tenant_id, context)

    logger.info("context_assembled", query=query[:50], chunks=len(chunks),
               tokens=token_estimate, intent=intent.intent.value, duration_ms=round(duration_ms, 2))

    return context


# --- Production Retrieval (real pgvector + tsvector) ---
# These async functions are used when environment == "production".
# The sync simulated functions above remain the default for dev/test.

async def async_dense_retrieval(query: str, tenant_id: str, top_k: int = 10) -> list[RetrievalChunk]:
    """Real pgvector cosine similarity search using embeddings."""
    from app.db import async_session
    from app.os_layer.embedding_service import get_embedding_service
    from sqlalchemy import text

    service = get_embedding_service()
    [query_embedding] = await service.embed([query])
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT chunk_id, content, source, 1 - (embedding <=> :emb::vector) as score
                FROM document_embeddings
                WHERE tenant_id = :tid
                ORDER BY embedding <=> :emb::vector
                LIMIT :k
            """),
            {"emb": embedding_str, "tid": tenant_id, "k": top_k},
        )
        rows = result.fetchall()

    return [
        RetrievalChunk(chunk_id=r[0], content=r[1], source=r[2], score=round(float(r[3]), 3), retrieval_method="dense")
        for r in rows
    ]


async def async_sparse_retrieval(query: str, tenant_id: str, top_k: int = 10) -> list[RetrievalChunk]:
    """Real PostgreSQL ts_rank full-text search with GIN index."""
    from app.db import async_session
    from sqlalchemy import text

    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT chunk_id, content, source,
                       ts_rank(content_tsv, plainto_tsquery('english', :q)) as score
                FROM document_embeddings
                WHERE tenant_id = :tid AND content_tsv @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT :k
            """),
            {"q": query, "tid": tenant_id, "k": top_k},
        )
        rows = result.fetchall()

    return [
        RetrievalChunk(chunk_id=r[0], content=r[1], source=r[2], score=round(float(r[3]), 3), retrieval_method="sparse")
        for r in rows
    ]


async def async_assemble_context(
    query: str,
    tenant_id: str,
    top_k: int = 5,
) -> AssembledContext:
    """Production context assembly using real pgvector + tsvector."""
    start = time.monotonic()
    intent = classify_intent(query)

    dense_results: list[RetrievalChunk] = []
    sparse_results: list[RetrievalChunk] = []

    if intent.intent in (RetrievalIntent.SEMANTIC, RetrievalIntent.HYBRID):
        dense_results = await async_dense_retrieval(query, tenant_id, top_k=top_k * 2)

    if intent.intent in (RetrievalIntent.STRUCTURED, RetrievalIntent.HYBRID, RetrievalIntent.LIVE):
        sparse_results = await async_sparse_retrieval(query, tenant_id, top_k=top_k * 2)

    if dense_results and sparse_results:
        chunks = reciprocal_rank_fusion(dense_results, sparse_results)[:top_k]
    elif dense_results:
        chunks = dense_results[:top_k]
    elif sparse_results:
        chunks = sparse_results[:top_k]
    else:
        chunks = []

    total_chars = sum(len(c.content) for c in chunks)
    duration_ms = (time.monotonic() - start) * 1000

    trace = RetrievalTrace(
        intent=intent, dense_results=len(dense_results), sparse_results=len(sparse_results),
        fused_results=len(chunks), cache_hit=False, retrieval_time_ms=round(duration_ms, 2),
    )

    return AssembledContext(
        query=query, chunks=chunks, total_tokens_estimate=total_chars // 4,
        retrieval_trace=trace, assembled_at=datetime.now(timezone.utc).isoformat(),
    )
