"""Context assembly routes — query context retrieval and re-ranking for agents."""

import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.middleware.auth import AuthContext, get_auth_context
from app.db import get_db
from app.os_layer.context import AssembledContext, ContextAssemblySubsystem
from app.schemas.response import APIResponse
from app.config import get_settings

router = APIRouter(prefix="/api/v1/context", tags=["context"])

class ContextRequest(BaseModel):
    """Request to assemble context for an agent query."""
    query: str
    top_k: int = 5
    use_cache: bool = True
    project_id: str | None = None

async def get_redis() -> Redis:
    """FastAPI dependency for Redis."""
    from redis.asyncio import from_url
    settings = get_settings()
    return from_url(settings.redis_url, decode_responses=True)

@router.post("/assemble", response_model=APIResponse[AssembledContext])
async def assemble(
    body: ContextRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[AssembledContext]:
    """Assemble relevant context using pgvector + Redis cache."""
    subsystem = ContextAssemblySubsystem(db, redis)
    
    project_id = None
    if body.project_id:
        project_id = uuid.UUID(body.project_id)
        
    ctx = await subsystem.assemble_context(
        tenant_id=uuid.UUID(auth.tenant_id),
        query=body.query,
        project_id=project_id,
        limit=body.top_k
    )
    return APIResponse(data=ctx)

@router.post("/ingest", response_model=APIResponse[dict])
async def ingest(
    content: str,
    source: str,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Ingest new knowledge into the RAG system."""
    subsystem = ContextAssemblySubsystem(db, redis)
    
    p_id = uuid.UUID(project_id) if project_id else None
    chunk_id = await subsystem.ingest_knowledge(
        tenant_id=uuid.UUID(auth.tenant_id),
        content=content,
        source=source,
        project_id=p_id
    )
    return APIResponse(data={"chunk_id": str(chunk_id)})
