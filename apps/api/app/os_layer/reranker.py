"""Cross-encoder re-ranker + token budget enforcer + parent-child retrieval.

Re-ranker: scores (query, chunk) pairs for relevance, drops below threshold.
TokenBudget: compresses context to fit within a step's token allocation.
Parent-child: embeds 256-token chunks, retrieves 1024-token parent documents.
"""

import hashlib
from pydantic import BaseModel

from app.os_layer.context import RetrievalChunk

import structlog

logger = structlog.get_logger()


# --- Cross-Encoder Re-ranker ---

RELEVANCE_THRESHOLD = 0.6


class RerankedChunk(BaseModel):
    """A chunk with re-ranker relevance score."""

    chunk_id: str
    content: str
    source: str
    original_score: float
    rerank_score: float
    passed_threshold: bool
    metadata: dict = {}


def _compute_rerank_score(query: str, content: str) -> float:
    """Simulate cross-encoder relevance scoring.

    In production: calls ms-marco-MiniLM model deployed on Railway (~100ms p95).
    For dev: uses word overlap ratio as a proxy.
    """
    query_words = set(query.lower().split())
    content_words = set(content.lower().split())

    if not query_words or not content_words:
        return 0.0

    # Overlap-based scoring as proxy for cross-encoder
    overlap = query_words & content_words
    query_coverage = len(overlap) / len(query_words)
    content_relevance = len(overlap) / min(len(content_words), 20)

    # Weighted combination
    score = (query_coverage * 0.6) + (content_relevance * 0.4)
    return round(min(1.0, score), 4)


def rerank_chunks(
    query: str,
    chunks: list[RetrievalChunk],
    threshold: float = RELEVANCE_THRESHOLD,
) -> list[RerankedChunk]:
    """Re-rank chunks using cross-encoder and filter below threshold.

    Args:
        query: The original search query.
        chunks: Chunks from hybrid retrieval.
        threshold: Minimum relevance score (default 0.6).

    Returns:
        Re-ranked and filtered chunks, sorted by rerank_score descending.
    """
    reranked = []
    for chunk in chunks:
        score = _compute_rerank_score(query, chunk.content)
        reranked.append(RerankedChunk(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            source=chunk.source,
            original_score=chunk.score,
            rerank_score=score,
            passed_threshold=score >= threshold,
            metadata=chunk.metadata,
        ))

    # Sort by rerank score descending
    reranked.sort(key=lambda c: c.rerank_score, reverse=True)

    # Filter below threshold
    passed = [c for c in reranked if c.passed_threshold]

    dropped = len(reranked) - len(passed)
    if dropped > 0:
        logger.info("reranker_filtered", total=len(reranked), passed=len(passed),
                    dropped=dropped, threshold=threshold)

    return passed


# --- Parent-Child Retrieval ---

class ParentChunk(BaseModel):
    """A parent document containing multiple child chunks."""

    parent_id: str
    content: str  # Full 1024-token parent
    source: str
    child_chunks: list[str]  # IDs of 256-token children
    token_count: int


# Simulated parent document store
_PARENT_DOCS: dict[str, ParentChunk] = {
    "p1": ParentChunk(
        parent_id="p1",
        content=(
            "The ShipBridge assessment engine evaluates AI agent systems across five pillars: "
            "reliability, security, eval, governance, and cost. Each pillar has dedicated scorers "
            "that analyze the project configuration. The reliability scorer checks for multi-model "
            "fallback, retry logic, and circuit breaker presence. The security scorer detects "
            "unauthenticated MCP endpoints and prompt injection surfaces. The eval scorer verifies "
            "CI grader presence and test coverage metrics. The governance scorer audits HITL gate "
            "configuration and ownership records. The cost scorer analyzes model routing tiers "
            "and semantic cache utilization. A total score of 75 or above is required for "
            "production deployment via the staged pipeline."
        ),
        source="docs/assessment.md",
        child_chunks=["d3"],
        token_count=128,
    ),
    "p2": ParentChunk(
        parent_id="p2",
        content=(
            "Circuit breakers in ShipBridge follow a three-state finite state machine: closed, "
            "open, and half-open. In the closed state, all requests pass through normally. After "
            "5 consecutive failures, the circuit transitions to open, blocking all requests. "
            "After a 30-second recovery timeout, the circuit moves to half-open, allowing one "
            "test request. If the test succeeds, the circuit closes. If it fails, the circuit "
            "reopens. Each connector has its own circuit breaker instance tracked in the "
            "ConnectorRegistry. The circuit breaker state is stored in Redis for cross-process "
            "sharing in production environments."
        ),
        source="docs/resilience.md",
        child_chunks=["d2"],
        token_count=112,
    ),
}

# Map child chunk IDs to parent IDs
_CHILD_TO_PARENT: dict[str, str] = {}
for pid, parent in _PARENT_DOCS.items():
    for child_id in parent.child_chunks:
        _CHILD_TO_PARENT[child_id] = pid


def expand_to_parents(chunks: list[RerankedChunk]) -> list[RerankedChunk]:
    """Expand 256-token child chunks to their 1024-token parent documents.

    If a child chunk has a parent, replace the child content with the
    fuller parent content for better agent context.
    """
    expanded = []
    seen_parents: set[str] = set()

    for chunk in chunks:
        parent_id = _CHILD_TO_PARENT.get(chunk.chunk_id)
        if parent_id and parent_id not in seen_parents:
            parent = _PARENT_DOCS.get(parent_id)
            if parent:
                seen_parents.add(parent_id)
                expanded.append(RerankedChunk(
                    chunk_id=f"{parent_id}:parent",
                    content=parent.content,
                    source=parent.source,
                    original_score=chunk.original_score,
                    rerank_score=chunk.rerank_score,
                    passed_threshold=chunk.passed_threshold,
                    metadata={**chunk.metadata, "expanded_from": chunk.chunk_id, "parent_tokens": parent.token_count},
                ))
                continue
        expanded.append(chunk)

    return expanded


# --- Token Budget Enforcer ---

class TokenBudget(BaseModel):
    """Token budget allocation for a context assembly step."""

    max_tokens: int
    used_tokens: int
    remaining_tokens: int
    chunks_included: int
    chunks_dropped: int


def enforce_token_budget(
    chunks: list[RerankedChunk],
    max_tokens: int = 4000,
) -> tuple[list[RerankedChunk], TokenBudget]:
    """Compress context to fit within the token budget.

    Includes chunks in order of relevance until the budget is exhausted.
    Token count estimated at ~4 chars per token.
    """
    included: list[RerankedChunk] = []
    used_tokens = 0
    dropped = 0

    for chunk in chunks:
        chunk_tokens = len(chunk.content) // 4
        if used_tokens + chunk_tokens <= max_tokens:
            included.append(chunk)
            used_tokens += chunk_tokens
        else:
            dropped += 1

    budget = TokenBudget(
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        remaining_tokens=max_tokens - used_tokens,
        chunks_included=len(included),
        chunks_dropped=dropped,
    )

    if dropped > 0:
        logger.info("token_budget_enforced", included=len(included), dropped=dropped,
                    used=used_tokens, max=max_tokens)

    return included, budget


# --- Full Re-rank + Budget Pipeline ---

class RerankResult(BaseModel):
    """Complete output of the re-rank + budget pipeline."""

    chunks: list[RerankedChunk]
    budget: TokenBudget
    reranked_count: int
    parent_expanded: int
    threshold_filtered: int


def rerank_and_budget(
    query: str,
    chunks: list[RetrievalChunk],
    max_tokens: int = 4000,
    relevance_threshold: float = RELEVANCE_THRESHOLD,
    expand_parents: bool = True,
) -> RerankResult:
    """Full pipeline: re-rank → threshold filter → parent expansion → token budget."""
    # Step 1: Re-rank and filter
    reranked = rerank_chunks(query, chunks, threshold=relevance_threshold)
    threshold_filtered = len(chunks) - len(reranked)

    # Step 2: Parent expansion
    parent_expanded = 0
    if expand_parents:
        before = len(reranked)
        reranked = expand_to_parents(reranked)
        parent_expanded = sum(1 for c in reranked if "expanded_from" in c.metadata)

    # Step 3: Token budget enforcement
    final_chunks, budget = enforce_token_budget(reranked, max_tokens=max_tokens)

    return RerankResult(
        chunks=final_chunks,
        budget=budget,
        reranked_count=len(chunks),
        parent_expanded=parent_expanded,
        threshold_filtered=threshold_filtered,
    )
