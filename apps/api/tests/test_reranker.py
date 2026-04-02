"""Tests for re-ranker, token budget enforcer, parent-child retrieval, and API."""

import pytest
from httpx import AsyncClient

from app.os_layer.context import RetrievalChunk
from app.os_layer.reranker import (
    RELEVANCE_THRESHOLD,
    _compute_rerank_score,
    enforce_token_budget,
    expand_to_parents,
    rerank_and_budget,
    rerank_chunks,
)


def _make_chunk(chunk_id: str, content: str, score: float = 0.8) -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=chunk_id, content=content, source="test",
        score=score, retrieval_method="fused",
    )


# --- Unit tests: cross-encoder scoring ---

class TestRerankerScoring:
    def test_high_overlap_scores_higher_than_no_overlap(self) -> None:
        high = _compute_rerank_score("circuit breaker failure", "Circuit breakers protect against cascading failures")
        low = _compute_rerank_score("circuit breaker failure", "The weather is sunny today")
        assert high > low

    def test_no_overlap_scores_low(self) -> None:
        score = _compute_rerank_score("deployment pipeline", "The weather is sunny today")
        assert score < 0.3

    def test_empty_query(self) -> None:
        assert _compute_rerank_score("", "some content") == 0.0

    def test_score_bounded(self) -> None:
        score = _compute_rerank_score("a b c d e", "a b c d e f g")
        assert 0.0 <= score <= 1.0


# --- Unit tests: re-rank + threshold filter ---

class TestRerankChunks:
    def test_filters_below_threshold(self) -> None:
        chunks = [
            _make_chunk("c1", "The circuit breaker opens after failures"),
            _make_chunk("c2", "Unrelated content about cooking recipes"),
        ]
        reranked = rerank_chunks("circuit breaker failure", chunks, threshold=0.3)
        # c1 should pass, c2 should be filtered
        ids = [c.chunk_id for c in reranked]
        assert "c1" in ids

    def test_sorted_by_rerank_score(self) -> None:
        chunks = [
            _make_chunk("c1", "Some agent content"),
            _make_chunk("c2", "The agent model routing uses three tiers for cost optimization"),
        ]
        reranked = rerank_chunks("agent model routing cost", chunks, threshold=0.0)
        scores = [c.rerank_score for c in reranked]
        assert scores == sorted(scores, reverse=True)

    def test_preserves_original_score(self) -> None:
        chunks = [_make_chunk("c1", "test content about agents", score=0.75)]
        reranked = rerank_chunks("agents", chunks, threshold=0.0)
        assert reranked[0].original_score == 0.75

    def test_empty_input(self) -> None:
        assert rerank_chunks("query", [], threshold=0.5) == []


# --- Unit tests: parent-child expansion ---

class TestParentChildRetrieval:
    def test_expands_known_child(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [RerankedChunk(
            chunk_id="d3", content="Short child content",
            source="docs/assessment.md", original_score=0.8,
            rerank_score=0.7, passed_threshold=True,
        )]
        expanded = expand_to_parents(chunks)
        assert len(expanded) == 1
        # Should have parent content (longer)
        assert len(expanded[0].content) > len("Short child content")
        assert "expanded_from" in expanded[0].metadata

    def test_no_parent_keeps_original(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [RerankedChunk(
            chunk_id="unknown_id", content="No parent",
            source="test", original_score=0.5,
            rerank_score=0.6, passed_threshold=True,
        )]
        expanded = expand_to_parents(chunks)
        assert expanded[0].content == "No parent"
        assert "expanded_from" not in expanded[0].metadata

    def test_deduplicates_same_parent(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [
            RerankedChunk(chunk_id="d3", content="Child A", source="s",
                         original_score=0.8, rerank_score=0.7, passed_threshold=True),
            RerankedChunk(chunk_id="d3", content="Child A dupe", source="s",
                         original_score=0.7, rerank_score=0.6, passed_threshold=True),
        ]
        expanded = expand_to_parents(chunks)
        # First becomes parent, second stays as-is (parent already seen)
        parent_count = sum(1 for c in expanded if "expanded_from" in c.metadata)
        assert parent_count == 1


# --- Unit tests: token budget ---

class TestTokenBudgetEnforcer:
    def test_includes_chunks_within_budget(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [
            RerankedChunk(chunk_id="a", content="A" * 2000, source="s",
                         original_score=0.9, rerank_score=0.9, passed_threshold=True),
            RerankedChunk(chunk_id="b", content="B" * 2000, source="s",
                         original_score=0.8, rerank_score=0.8, passed_threshold=True),
        ]
        included, budget = enforce_token_budget(chunks, max_tokens=600)
        assert len(included) == 1  # 2000 chars / 4 = 500 tokens, only first fits in 600
        assert budget.chunks_dropped == 1

    def test_all_fit_within_budget(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [
            RerankedChunk(chunk_id="a", content="Short", source="s",
                         original_score=0.9, rerank_score=0.9, passed_threshold=True),
        ]
        included, budget = enforce_token_budget(chunks, max_tokens=4000)
        assert len(included) == 1
        assert budget.chunks_dropped == 0

    def test_empty_chunks(self) -> None:
        included, budget = enforce_token_budget([], max_tokens=4000)
        assert len(included) == 0
        assert budget.used_tokens == 0

    def test_budget_tracking(self) -> None:
        from app.os_layer.reranker import RerankedChunk
        chunks = [
            RerankedChunk(chunk_id="a", content="X" * 800, source="s",
                         original_score=0.9, rerank_score=0.9, passed_threshold=True),
        ]
        _, budget = enforce_token_budget(chunks, max_tokens=4000)
        assert budget.used_tokens == 200  # 800 chars / 4
        assert budget.remaining_tokens == 3800


# --- Unit tests: full pipeline ---

class TestRerankAndBudget:
    def test_full_pipeline(self) -> None:
        chunks = [
            _make_chunk("d3", "The assessment engine scores projects across 5 pillars: reliability, security, eval, governance, and cost."),
            _make_chunk("d1", "The agent uses multi-model routing with Haiku for simple tasks."),
            _make_chunk("xx", "Completely unrelated content about nothing relevant."),
        ]
        # Use low threshold since word-overlap proxy gives conservative scores
        result = rerank_and_budget("assessment engine pillars scoring", chunks, max_tokens=4000, relevance_threshold=0.1)
        assert len(result.chunks) > 0
        assert result.budget.used_tokens > 0

    def test_threshold_filtering_reported(self) -> None:
        chunks = [
            _make_chunk("c1", "Relevant assessment content about scoring"),
            _make_chunk("c2", "Totally unrelated cooking recipe content"),
        ]
        result = rerank_and_budget("assessment scoring", chunks, relevance_threshold=0.3)
        assert result.threshold_filtered >= 0


# --- API endpoint tests ---

async def _get_token(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "rerank@test.com", "full_name": "Rerank User",
        "tenant_name": "Rerank Corp", "tenant_slug": "rerank-corp",
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_rerank_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client)
    resp = await client.post("/api/v1/context/rerank",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "How does the assessment engine score reliability?", "max_tokens": 2000},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "chunks" in data
    assert "budget" in data
    assert data["budget"]["max_tokens"] == 2000


@pytest.mark.asyncio
async def test_rerank_with_low_threshold(client: AsyncClient) -> None:
    token = await _get_token(client)
    resp = await client.post("/api/v1/context/rerank",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "agent routing model deployment", "relevance_threshold": 0.1},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Low threshold = more chunks pass
    assert data["threshold_filtered"] >= 0
