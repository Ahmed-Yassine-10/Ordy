"""Envelope encryption for restaurant-supplied credentials (doc 08 §4).

Restaurant DB strings, POS tokens, Action Provider tokens and webhook secrets are stored
ONLY as ciphertext; everything else references them as `vault:sec_…`. A per-secret data
key (DEK) is wrapped by a KMS master key, so rotating the master never rewrites rows.

**Cipher choice is deliberate**: production uses AES-GCM via `cryptography` with a cloud
KMS `KeyManager`. This module ships no homemade cipher — the test double is explicitly
named insecure so it can never be mistaken for a production path.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Protocol


class KeyManager(Protocol):
    """Wraps/unwraps data keys. Backed by cloud KMS in production."""

    def generate_dek(self) -> bytes: ...
    def wrap(self, dek: bytes) -> bytes: ...
    def unwrap(self, wrapped: bytes) -> bytes: ...


class Cipher(Protocol):
    def encrypt(self, key: bytes, plaintext: bytes, *, aad: bytes = b"") -> tuple[bytes, bytes]: ...
    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, *, aad: bytes = b"") -> bytes: ...


@dataclass(slots=True)
class EnvelopeSecret:
    """What actually lands in the database column."""

    wrapped_dek: bytes
    nonce: bytes
    ciphertext: bytes
    key_id: str = "kms:primary"

    def to_blob(self) -> bytes:
        parts = [self.key_id.encode(), self.wrapped_dek, self.nonce, self.ciphertext]
        return b".".join(base64.urlsafe_b64encode(p) for p in parts)

    @classmethod
    def from_blob(cls, blob: bytes) -> "EnvelopeSecret":
        key_id, wrapped, nonce, ciphertext = (base64.urlsafe_b64decode(p) for p in blob.split(b"."))
        return cls(wrapped_dek=wrapped, nonce=nonce, ciphertext=ciphertext, key_id=key_id.decode())


class AesGcmCipher:
    """Production cipher. Requires the `cryptography` package."""

    def encrypt(self, key: bytes, plaintext: bytes, *, aad: bytes = b"") -> tuple[bytes, bytes]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

        nonce = os.urandom(12)
        return nonce, AESGCM(key).encrypt(nonce, plaintext, aad)

    def decrypt(self, key: bytes, nonce: bytes, ciphertext: bytes, *, aad: bytes = b"") -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

        return AESGCM(key).decrypt(nonce, ciphertext, aad)


def encrypt_secret(plaintext: str, *, km: KeyManager, cipher: Cipher, aad: bytes = b"") -> EnvelopeSecret:
    dek = km.generate_dek()
    nonce, ciphertext = cipher.encrypt(dek, plaintext.encode(), aad=aad)
    return EnvelopeSecret(wrapped_dek=km.wrap(dek), nonce=nonce, ciphertext=ciphertext)


def decrypt_secret(secret: EnvelopeSecret, *, km: KeyManager, cipher: Cipher, aad: bytes = b"") -> str:
    dek = km.unwrap(secret.wrapped_dek)
    return cipher.decrypt(dek, secret.nonce, secret.ciphertext, aad=aad).decode()


def is_vault_ref(value: object) -> bool:
    """Configs must carry references, never plaintext (doc 08 §4)."""
    return isinstance(value, str) and value.startswith("vault:")


def assert_no_plaintext_secrets(config: dict, secret_keys: tuple[str, ...]) -> None:
    """Guard used when saving source/tool configs: a credential-shaped key must hold a
    `vault:` reference, never the credential itself."""
    for key, value in config.items():
        normalized = key.lower()
        if any(marker in normalized for marker in secret_keys) and value and not is_vault_ref(value):
            raise ValueError(f"'{key}' must be a vault reference, not a literal secret")
