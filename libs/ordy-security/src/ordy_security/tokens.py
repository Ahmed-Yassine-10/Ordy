"""JWT access tokens + opaque, hashed refresh tokens (doc 08 §2, ADR-013).

Access tokens are short-lived signed JWTs (stateless). Refresh tokens are opaque
random strings stored only as SHA-256 hashes with rotation + reuse detection.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt


class TokenError(Exception):
    """Raised when a token is invalid, expired, or malformed."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    is_platform_admin: bool
    expires_at: int


def encode_access_token(
    *,
    user_id: uuid.UUID,
    secret: str,
    ttl_seconds: int,
    issuer: str,
    is_platform_admin: bool = False,
    now: int | None = None,
) -> str:
    issued = now if now is not None else int(time.time())
    payload = {
        "sub": str(user_id),
        "adm": is_platform_admin,
        "iss": issuer,
        "iat": issued,
        "exp": issued + ttl_seconds,
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str, issuer: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:  # noqa: BLE001 — normalize to our error
        raise TokenError(str(exc)) from exc
    if payload.get("typ") != "access":
        raise TokenError("not an access token")
    return AccessClaims(
        user_id=uuid.UUID(payload["sub"]),
        is_platform_admin=bool(payload.get("adm", False)),
        expires_at=int(payload["exp"]),
    )


def new_refresh_token() -> str:
    """Opaque, URL-safe refresh token. The plaintext is returned to the client once."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
