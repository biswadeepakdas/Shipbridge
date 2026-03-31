"""ConnectorAdapter abstract base class — interface for all external service connectors."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConnectorHealthResult(BaseModel):
    """Result from a connector health check."""

    status: str  # "healthy", "degraded", "down"
    latency_ms: float
    error_message: str | None = None
    checked_at: str


class NormalizedData(BaseModel):
    """Normalized output from a connector fetch — agent-friendly markdown."""

    source: str
    data_type: str
    content: str  # markdown-formatted
    metadata: dict = {}
    fetched_at: str


class ConnectorAdapter(ABC):
    """Abstract base class for all external service connectors.

    Every adapter must implement fetch(), health_check(), and normalize().
    """

    adapter_type: str = "base"

    @abstractmethod
    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch raw data from the external service.

        Args:
            query: Service-specific query parameters.

        Returns:
            Raw response data from the external API.
        """

    @abstractmethod
    async def health_check(self) -> ConnectorHealthResult:
        """Check connectivity and latency to the external service.

        Returns:
            Health status with latency measurement.
        """

    @abstractmethod
    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform raw API data into agent-friendly normalized format.

        Args:
            raw_data: Raw response from fetch().

        Returns:
            Normalized markdown content for agent consumption.
        """
