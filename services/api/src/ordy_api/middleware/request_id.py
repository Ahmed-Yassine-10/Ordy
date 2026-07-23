"""Assigns/propagates a request ID for tracing + problem+json ``instance`` (doc 01 §6)."""

from __future__ import annotations

from ordy_core.ids import display_id, uuid7
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID") or display_id("req", uuid7())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
