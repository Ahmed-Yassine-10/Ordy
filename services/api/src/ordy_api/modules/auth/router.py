from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request, Response, status
from ordy_core.db import Database
from ordy_core.errors import Unauthenticated
from ordy_core.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import Settings, get_settings
from ordy_api.deps import Scope, get_scope
from ordy_api.modules.auth import service
from ordy_api.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "ordy_refresh"


async def _plain_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A committed transaction with NO tenant context — for identity tables only."""
    db: Database = request.app.state.db
    async with db.session() as session:
        yield session


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        token,
        max_age=settings.jwt_refresh_ttl_seconds,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        path="/v1/auth",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, session: AsyncSession = Depends(_plain_session)
) -> User:
    return await service.register(
        session, email=body.email, password=body.password, name=body.name
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(_plain_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    _, access, refresh = await service.login(
        session, email=body.email, password=body.password, settings=settings
    )
    _set_refresh_cookie(response, refresh, settings)
    return TokenResponse(
        access_token=access,
        expires_in=settings.jwt_access_ttl_seconds,
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(_plain_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    token = (body.refresh_token if body else None) or request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise Unauthenticated("no refresh token provided")
    access, new_refresh = await service.refresh_tokens(
        session, refresh_token=token, settings=settings
    )
    _set_refresh_cookie(response, new_refresh, settings)
    return TokenResponse(
        access_token=access,
        expires_in=settings.jwt_access_ttl_seconds,
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(_plain_session),
) -> None:
    token = (body.refresh_token if body else None) or request.cookies.get(_REFRESH_COOKIE)
    if token:
        await service.logout(session, refresh_token=token)
    response.delete_cookie(_REFRESH_COOKIE, path="/v1/auth")


@router.get("/me", response_model=UserOut)
async def me(scope: Scope = Depends(get_scope)) -> User:
    if scope.principal.user_id is None:
        raise Unauthenticated("this endpoint requires a user session")
    user = await scope.session.get(User, scope.principal.user_id)
    if user is None:
        raise Unauthenticated("user no longer exists")
    return user
