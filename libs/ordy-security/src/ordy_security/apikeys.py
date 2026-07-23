"""Machine API keys (ADR-013). Format: ``ordy_{env}_{32 url-safe chars}``.

Only the SHA-256 hash is stored; the plaintext is shown once at creation. A short
prefix is stored separately so keys are identifiable in the dashboard and lookups
can be narrowed before the constant-time hash comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

_PREFIX_LEN = 16  # e.g. "ordy_live_a1b2c3" — displayed, safe to store in clear


@dataclass(frozen=True, slots=True)
class ApiKeyParts:
    plaintext: str  # returned to the caller exactly once
    prefix: str  # stored for display + lookup
    key_hash: bytes  # stored; never reversible


def generate_api_key(env: str = "live") -> ApiKeyParts:
    body = secrets.token_urlsafe(24)
    plaintext = f"ordy_{env}_{body}"
    return ApiKeyParts(
        plaintext=plaintext,
        prefix=plaintext[:_PREFIX_LEN],
        key_hash=hash_api_key(plaintext),
    )


def hash_api_key(plaintext: str) -> bytes:
    return hashlib.sha256(plaintext.encode("utf-8")).digest()


def verify_api_key(plaintext: str, expected_hash: bytes) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext), expected_hash)


def prefix_of(plaintext: str) -> str:
    return plaintext[:_PREFIX_LEN]
