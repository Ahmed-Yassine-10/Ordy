"""Auth service: registration, login, refresh rotation with reuse detection.

Operates on identity tables (no tenant RLS). Access tokens are stateless JWTs;
refresh tokens are opaque, stored only as hashes, and rotated on every use.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from ordy_core.errors import EmailTaken, InvalidCredentials, InvalidToken
from ordy_core.ids import uuid7
from ordy_core.models import RefreshToken, User
from ordy_security import (
    encode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import Settings


async def register(session: AsyncSession, *, email: str, password: str, name: str) -> User:
    exists = await session.scalar(select(User.id).where(User.email == email))
    if exists is not None:
        raise EmailTaken("an account with this email already exists")
    user = User(email=email, name=name, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def _issue_refresh(
    session: AsyncSession, *, user_id: uuid.UUID, settings: Settings, family_id: uuid.UUID
) -> str:
    plaintext = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(plaintext),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
        )
    )
    return plaintext


def _issue_access(user: User, settings: Settings) -> str:
    return encode_access_token(
        user_id=user.id,
        secret=settings.jwt_secret,
        ttl_seconds=settings.jwt_access_ttl_seconds,
        issuer=settings.jwt_issuer,
        is_platform_admin=user.is_platform_admin,
    )


async def login(
    session: AsyncSession, *, email: str, password: str, settings: Settings
) -> tuple[User, str, str]:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or user.password_hash is None:
        raise InvalidCredentials("invalid email or password")
    if not verify_password(user.password_hash, password):
        raise InvalidCredentials("invalid email or password")
    user.last_login_at = datetime.now(UTC)
    access = _issue_access(user, settings)
    refresh = await _issue_refresh(
        session, user_id=user.id, settings=settings, family_id=uuid7()
    )
    return user, access, refresh


async def refresh_tokens(
    session: AsyncSession, *, refresh_token: str, settings: Settings
) -> tuple[str, str]:
    token_hash = hash_refresh_token(refresh_token)
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is None:
        raise InvalidToken("unknown refresh token")

    # Reuse detection: a token presented after it was already rotated/revoked means
    # the family is compromised — revoke the whole chain (doc 08 §2).
    if row.revoked_at is not None:
        await _revoke_family(session, row.family_id)
        raise InvalidToken("refresh token reuse detected; session revoked")
    if row.expires_at < datetime.now(UTC):
        raise InvalidToken("refresh token expired")

    user = await session.get(User, row.user_id)
    if user is None:
        raise InvalidToken("user no longer exists")

    row.revoked_at = datetime.now(UTC)
    new_plain = await _issue_refresh(
        session, user_id=user.id, settings=settings, family_id=row.family_id
    )
    access = _issue_access(user, settings)
    return access, new_plain


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    rows = await session.scalars(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    for token in rows:
        token.revoked_at = now


async def logout(session: AsyncSession, *, refresh_token: str) -> None:
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
    )
    if row is not None:
        await _revoke_family(session, row.family_id)
