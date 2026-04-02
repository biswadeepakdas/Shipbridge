"""Custom exceptions and FastAPI exception handler."""

from enum import Enum

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.response import APIError, APIResponse


class ErrorCode(str, Enum):
    """Machine-readable error codes."""

    TIMEOUT = "TIMEOUT"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION = "VALIDATION_ERROR"
    INTERNAL = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


HTTP_STATUS_MAP = {
    ErrorCode.TIMEOUT: 504,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.VALIDATION: 422,
    ErrorCode.INTERNAL: 500,
    ErrorCode.RATE_LIMITED: 429,
}


class AppError(Exception):
    """Application error that maps to an API error response."""

    def __init__(self, code: ErrorCode, message: str, details: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError to standard API envelope."""
    status = HTTP_STATUS_MAP.get(exc.code, 500)
    body = APIResponse(
        error=APIError(code=exc.code.value, message=exc.message, details=exc.details)
    )
    return JSONResponse(status_code=status, content=body.model_dump())
