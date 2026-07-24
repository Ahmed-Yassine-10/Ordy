"""FastAPI application factory + middleware chain + router mounting (doc 01 §4.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ordy_core.db import Database
from ordy_core.errors import OrdyError

from ordy_api.config import get_settings
from ordy_api.middleware import RequestIdMiddleware
from ordy_api.modules import (
    agent,
    auth,
    health,
    knowledge,
    menu,
    orders,
    privacy,
    restaurants,
    tools,
    workflows,
)
from ordy_api.problems import ordy_error_handler, unhandled_error_handler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.db = Database(settings.database_url, echo=settings.db_echo)
    try:
        yield
    finally:
        await app.state.db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Ordy API",
        version="0.1.0",
        description="The AI waiter that understands, talks, and takes action.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.add_exception_handler(OrdyError, ordy_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/v1")
    app.include_router(restaurants.router, prefix="/v1")
    app.include_router(menu.router, prefix="/v1")
    app.include_router(knowledge.router, prefix="/v1")
    app.include_router(agent.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")
    app.include_router(orders.router, prefix="/v1")
    app.include_router(orders.public_router, prefix="/v1")
    app.include_router(workflows.router, prefix="/v1")
    app.include_router(privacy.router, prefix="/v1")

    return app


app = create_app()
