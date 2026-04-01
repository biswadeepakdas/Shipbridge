"""EmbeddingService — generate vector embeddings for text chunks.

Provides ABC + two implementations:
- OpenAIEmbeddingService: real API calls for production
- SimulatedEmbeddingService: hash-based fallback for dev/test
"""

import hashlib
from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger()


class EmbeddingService(ABC):
    """Abstract embedding service."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for the given texts."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""


class OpenAIEmbeddingService(EmbeddingService):
    """Uses OpenAI-compatible embedding API (works with OpenAI, Anthropic proxy, etc.)."""

    def __init__(self, api_url: str, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Call embedding API and return vectors."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._api_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": texts, "model": self._model},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]

    def dimension(self) -> int:
        return 1536


class SimulatedEmbeddingService(EmbeddingService):
    """Hash-based embedding simulation for dev/test. No external API calls."""

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h[: self._dim]]
            results.append(vec)
        return results

    def dimension(self) -> int:
        return self._dim


# Singleton — defaults to simulated for dev/test
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the current embedding service (simulated by default)."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = SimulatedEmbeddingService()
    return _embedding_service


def set_embedding_service(service: EmbeddingService) -> None:
    """Override the embedding service (e.g., for production)."""
    global _embedding_service
    _embedding_service = service
