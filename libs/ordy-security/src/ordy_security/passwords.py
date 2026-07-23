"""Password hashing with Argon2id (doc 08 §2)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Defaults are OWASP-reasonable; tune with load testing before GA.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        return _hasher.verify(hashed, plaintext)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when parameters have since been strengthened; caller should re-hash."""
    return _hasher.check_needs_rehash(hashed)
