"""Standard API response envelope — used by all endpoints."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIError(BaseModel):
    """Machine-readable error with human-friendly message."""

    code: str
    message: str
    details: dict = {}


class APIResponse(BaseModel, Generic[T]):
    """Envelope wrapping all API responses."""

    data: T | None = None
    error: APIError | None = None
    meta: dict = {}
