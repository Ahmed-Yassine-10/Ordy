"""Domain error hierarchy + stable error codes (doc 07 §7).

The API layer maps these to RFC 7807 problem+json; the agent's Conversation
node maps the same ``code`` values to graceful spoken repairs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    # auth / access
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    TOKEN_INVALID = "TOKEN_INVALID"
    # generic
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    # domain (action pipeline — populated in later phases)
    TOOL_NOT_ENABLED = "TOOL_NOT_ENABLED"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_UNAVAILABLE = "PRODUCT_UNAVAILABLE"
    OUTSIDE_OPERATING_HOURS = "OUTSIDE_OPERATING_HOURS"
    ORDER_ABOVE_CAP = "ORDER_ABOVE_CAP"


class OrdyError(Exception):
    """Base class for expected, mappable domain errors."""

    status: int = 400
    code: ErrorCode = ErrorCode.VALIDATION_FAILED

    def __init__(self, detail: str, *, meta: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.meta = meta or {}


class Unauthenticated(OrdyError):
    status = 401
    code = ErrorCode.UNAUTHENTICATED


class InvalidCredentials(OrdyError):
    status = 401
    code = ErrorCode.INVALID_CREDENTIALS


class InvalidToken(OrdyError):
    status = 401
    code = ErrorCode.TOKEN_INVALID


class Forbidden(OrdyError):
    status = 403
    code = ErrorCode.FORBIDDEN


class NotFound(OrdyError):
    status = 404
    code = ErrorCode.NOT_FOUND


class Conflict(OrdyError):
    status = 409
    code = ErrorCode.CONFLICT


class EmailTaken(Conflict):
    code = ErrorCode.EMAIL_TAKEN


class ValidationFailed(OrdyError):
    status = 422
    code = ErrorCode.VALIDATION_FAILED
