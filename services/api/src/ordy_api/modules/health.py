"""Liveness + readiness probes.

The distinction matters in production: **liveness must not depend on the database**. If it
did, a brief Postgres blip would make the kubelet restart every API pod at once, turning a
recoverable dependency hiccup into a self-inflicted outage. Readiness *does* check the
database — an instance that can't reach it should stop taking traffic while staying alive.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness: is the process itself healthy? No external dependencies by design."""
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    """Readiness: can this instance actually serve traffic (database reachable)?"""
    db = getattr(request.app.state, "db", None)
    if db is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "starting"}
    try:
        async with db.session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — a probe reports status, it never raises
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded"}
    return {"status": "ready"}
