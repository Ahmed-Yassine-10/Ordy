"""Liveness + readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    db = request.app.state.db
    async with db.session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
