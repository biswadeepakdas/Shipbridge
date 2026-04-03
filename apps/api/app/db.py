from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


@lru_cache
def _get_engine() -> AsyncEngine:
    """Lazily create the async engine on first use (not at import time)."""
    from app.config import get_settings
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
        pool_pre_ping=True,
    )


@lru_cache
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)


# Public aliases — existing code that references `engine` / `async_session` continues to work
# via module-level attribute access.
def __getattr__(name: str):
    if name == "engine":
        return _get_engine()
    if name == "async_session":
        return _get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with _get_session_factory()() as session:
        yield session
