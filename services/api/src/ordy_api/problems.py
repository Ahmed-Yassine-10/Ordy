"""RFC 7807 problem+json mapping for domain errors (doc 07 §1)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ordy_core.errors import OrdyError

_DOCS_BASE = "https://docs.ordy.ai/errors/"


def _problem(status: int, code: str, title: str, detail: str, request: Request, meta: dict) -> JSONResponse:
    body = {
        "type": f"{_DOCS_BASE}{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": getattr(request.state, "request_id", None),
    }
    if meta:
        body["meta"] = meta
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


async def ordy_error_handler(request: Request, exc: OrdyError) -> JSONResponse:
    return _problem(
        exc.status,
        exc.code.value,
        exc.code.value.replace("_", " ").title(),
        exc.detail,
        request,
        exc.meta,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals (doc 08 §6.3). Details go to logs/traces, not the client.
    return _problem(
        500,
        "INTERNAL_ERROR",
        "Internal Server Error",
        "An unexpected error occurred.",
        request,
        {},
    )
