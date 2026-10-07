"""Consistent API error envelope (spec §55).

Every error response has the shape:

    {"error": {"code": "...", "message": "...", "details": ...}}
"""

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import logger


class ErrorCode(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    AI_GENERATION_FAILED = "AI_GENERATION_FAILED"
    SOURCE_API_FAILED = "SOURCE_API_FAILED"
    CRAWL_FAILED = "CRAWL_FAILED"
    FILE_UPLOAD_FAILED = "FILE_UPLOAD_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.INVALID_STATE_TRANSITION: 409,
    ErrorCode.AI_GENERATION_FAILED: 502,
    ErrorCode.SOURCE_API_FAILED: 502,
    ErrorCode.CRAWL_FAILED: 502,
    ErrorCode.FILE_UPLOAD_FAILED: 400,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
}

_HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or _DEFAULT_STATUS[code]
        self.details = details
        self.headers = headers


class NotFound(AppError):
    def __init__(self, entity: str = "Resource") -> None:
        super().__init__(ErrorCode.NOT_FOUND, f"{entity} not found.")


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(ErrorCode.FORBIDDEN, message)


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(ErrorCode.UNAUTHORIZED, message)


class Conflict(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFLICT, message)


class InvalidStateTransition(AppError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(ErrorCode.INVALID_STATE_TRANSITION, message, details=details)


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(ErrorCode.VALIDATION_ERROR, "Request validation failed.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred."),
        )
