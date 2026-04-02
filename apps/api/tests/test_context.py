"""Tests for context assembly — intent classifier, retrieval, fusion, cache, API."""

import pytest
from httpx import AsyncClient

from app.os_layer.context import (
    ContextCache,
    RetrievalIntent,
    assemble_context,
    classify_intent,
    dense_retrieval,
    reciprocal_rank_fusion,
    sparse_retrieval,
    context_cache,
)


# --- Unit tests: intent classification ---

class TestIntentClassification:
    def test_structured_query(self) -> None:
        result = classify_intent("How many active projects do we have?")
        assert result.intent == RetrievalIntent.STRUCTURED

    def test_semantic_query(self) -> None:
        result = classify_intent("Explain how the circuit breaker pattern works")
        assert result.intent == RetrievalIntent.SEMANTIC

    def test_live_query(self) -> None:
        result = classify_intent("What is the current status of the deployment right now?")
        assert result.intent == RetrievalIntent.LIVE

    def test_hybrid_default(self) -> None:
        result = classify_intent("agent deployment pipeline circuit breaker")
        assert result.intent == RetrievalIntent.HYBRID

    def test_confidence_above_zero(self) -> None:
        result = classify_intent("anything")
        assert result.confidence > 0


# --- Unit tests: dense retrieval ---

class TestDenseRetrieval:
    def test_returns_relevant_chunks(self) -> None:
        chunks = dense_retrieval("circuit breaker failure resilience", "t1")
        assert len(chunks) > 0
        assert any("circuit" in c.content.lower() for c in chunks)

    def test_scores_are_descending(self) -> None:
        chunks = dense_retrieval("agent model routing", "t1")
        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)

    def test_empty_query_returns_empty(self) -> None:
        chunks = dense_retrieval("xyznonexistent", "t1")
        assert len(chunks) == 0

    def test_respects_top_k(self) -> None:
        chunks = dense_retrieval("agent deployment assessment", "t1", top_k=2)
        assert len(chunks) <= 2


# --- Unit tests: sparse retrieval ---

class TestSparseRetrieval:
    def test_returns_relevant_chunks(self) -> None:
        chunks = sparse_retrieval("security api key hmac", "t1")
        assert len(chunks) > 0

    def test_keyword_matching(self) -> None:
        chunks = sparse_retrieval("webhook signature verify", "t1")
        assert any("webhook" in c.content.lower() for c in chunks)


# --- Unit tests: reciprocal rank fusion ---

class TestReciprocalRankFusion:
    def test_merges_results(self) -> None:
        from app.os_layer.context import RetrievalChunk
        dense = [
            RetrievalChunk(chunk_id="a", content="A", source="s", score=0.9, retrieval_method="dense"),
            RetrievalChunk(chunk_id="b", content="B", source="s", score=0.8, retrieval_method="dense"),
        ]
        sparse = [
            RetrievalChunk(chunk_id="b", content="B", source="s", score=0.85, retrieval_method="sparse"),
            RetrievalChunk(chunk_id="c", content="C", source="s", score=0.7, retrieval_method="sparse"),
        ]
        fused = reciprocal_rank_fusion(dense, sparse)
        assert len(fused) == 3
        # "b" appears in both, should rank highest
        assert fused[0].chunk_id == "b"
        assert all(c.retrieval_method == "fused" for c in fused)

    def test_deduplicates_chunks(self) -> None:
        from app.os_layer.context import RetrievalChunk
        dense = [RetrievalChunk(chunk_id="x", content="X", source="s", score=0.9, retrieval_method="dense")]
        sparse = [RetrievalChunk(chunk_id="x", content="X", source="s", score=0.8, retrieval_method="sparse")]
        fused = reciprocal_rank_fusion(dense, sparse)
        assert len(fused) == 1

    def test_empty_inputs(self) -> None:
        fused = reciprocal_rank_fusion([], [])
        assert len(fused) == 0


# --- Unit tests: context cache ---

class TestContextCache:
    def test_cache_miss_then_hit(self) -> None:
        cache = ContextCache()
        assert cache.get("q", "t") is None  # miss
        ctx = assemble_context("agent routing model", "t1", use_cache=False)
        cache.put("q", "t", ctx)
        assert cache.get("q", "t") is not None  # hit

    def test_hit_rate_tracking(self) -> None:
        cache = ContextCache()
        cache.get("a", "t")  # miss
        ctx = assemble_context("test", "t1", use_cache=False)
        cache.put("b", "t", ctx)
        cache.get("b", "t")  # hit
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 1
        assert cache.stats["hit_rate"] == 0.5


# --- Unit tests: full assembly ---

class TestContextAssembly:
    def test_assembles_context_for_hybrid_query(self) -> None:
        ctx = assemble_context("agent deployment assessment reliability", "t1", use_cache=False)
        assert len(ctx.chunks) > 0
        assert ctx.total_tokens_estimate > 0
        assert ctx.retrieval_trace.intent.intent in (RetrievalIntent.HYBRID, RetrievalIntent.SEMANTIC)

    def test_assembles_context_for_semantic_query(self) -> None:
        ctx = assemble_context("explain how the assessment engine works", "t1", use_cache=False)
        assert ctx.retrieval_trace.intent.intent == RetrievalIntent.SEMANTIC
        assert ctx.retrieval_trace.dense_results > 0

    def test_cache_integration(self) -> None:
        # Reset cache
        context_cache._store.clear()
        context_cache._hits = 0
        context_cache._misses = 0

        ctx1 = assemble_context("agent model routing", "t1", use_cache=True)
        assert ctx1.retrieval_trace.cache_hit is False

        ctx2 = assemble_context("agent model routing", "t1", use_cache=True)
        assert ctx2.retrieval_trace.cache_hit is True

    def test_respects_top_k(self) -> None:
        ctx = assemble_context("agent deployment assessment cost security", "t1", top_k=2, use_cache=False)
        assert len(ctx.chunks) <= 2


# --- API endpoint tests ---

async def _get_token(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "ctx@test.com", "full_name": "Ctx User",
        "tenant_name": "Ctx Corp", "tenant_slug": "ctx-corp",
    })
    return resp.json()["data"]["token"]["access_token"]


@pytest.mark.asyncio
async def test_context_assemble_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client)
    resp = await client.post("/api/v1/context/assemble",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "How does the assessment engine score reliability?", "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["chunks"]) > 0
    assert data["total_tokens_estimate"] > 0
    assert "retrieval_trace" in data


@pytest.mark.asyncio
async def test_cache_stats_endpoint(client: AsyncClient) -> None:
    token = await _get_token(client)
    resp = await client.get("/api/v1/context/cache-stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "hits" in data
    assert "hit_rate" in data
