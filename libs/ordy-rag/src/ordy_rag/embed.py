"""Embedding port (ADR-008) + a deterministic hashing embedder for dev/tests.

``HashingEmbedder`` maps token bags into a fixed-dim, L2-normalized vector using a
stable hash — no network, fully reproducible, good enough to exercise vector search
and RRF end to end. Production uses the model router's EMBEDDING tier behind the same
``Embedder`` protocol.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9؀-ۿ]+")  # latin + arabic ranges


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbedder:
    """Returns zero vectors — retrieval degrades to lexical-only. Safe default."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder (dev/tests)."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self.dim
            sign = 1.0 if digest[0] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]
