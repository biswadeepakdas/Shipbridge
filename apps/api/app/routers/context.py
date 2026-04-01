"""Context assembly routes — query context retrieval and re-ranking for agents."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import AuthContext, get_auth_context
from app.os_layer.context import AssembledContext, RetrievalChunk, assemble_context, context_cache
from app.os_layer.reranker import RerankResult, rerank_and_budget
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/context", tags=["context"])


class ContextRequest(BaseModel):
    """Request to assemble context for an agent query."""

    query: str
    top_k: int = 5
    use_cache: bool = True
    max_tokens: int = 4000
    rerank: bool = True
    relevance_threshold: float = 0.6


@router.post("/assemble", response_model=APIResponse[AssembledContext])
async def assemble(
    body: ContextRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[AssembledContext]:
    """Assemble relevant context with optional re-ranking and token budget."""
    ctx = assemble_context(
        query=body.query,
        tenant_id=auth.tenant_id,
        top_k=body.top_k,
        use_cache=body.use_cache,
    )
    return APIResponse(data=ctx)


@router.post("/rerank", response_model=APIResponse[RerankResult])
async def rerank(
    body: ContextRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[RerankResult]:
    """Assemble context then apply re-ranker + token budget pipeline."""
    ctx = assemble_context(
        query=body.query,
        tenant_id=auth.tenant_id,
        top_k=body.top_k * 2,  # Fetch more for re-ranking to filter
        use_cache=body.use_cache,
    )

    result = rerank_and_budget(
        query=body.query,
        chunks=ctx.chunks,
        max_tokens=body.max_tokens,
        relevance_threshold=body.relevance_threshold,
    )
    return APIResponse(data=result)


@router.get("/cache-stats", response_model=APIResponse[dict])
async def cache_stats(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Get context cache statistics."""
    return APIResponse(data=context_cache.stats)
