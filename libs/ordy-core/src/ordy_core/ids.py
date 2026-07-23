"""Time-ordered UUIDv7 primary keys + human-friendly prefixed display IDs.

UUIDv7 (draft RFC 9562) sorts by creation time, which keeps B-tree and HNSW
indexes compact. Python's stdlib gains ``uuid.uuid7`` only in 3.14, so we
generate it here.
"""

from __future__ import annotations

import os
import time
import uuid

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"  # no i/l/o/u — display only


def uuid7() -> uuid.UUID:
    """Return a UUIDv7: 48-bit ms timestamp + 74 random bits, version/variant set."""
    unix_ms = time.time_ns() // 1_000_000
    rand = os.urandom(10)
    b = bytearray(16)
    b[0] = (unix_ms >> 40) & 0xFF
    b[1] = (unix_ms >> 32) & 0xFF
    b[2] = (unix_ms >> 24) & 0xFF
    b[3] = (unix_ms >> 16) & 0xFF
    b[4] = (unix_ms >> 8) & 0xFF
    b[5] = unix_ms & 0xFF
    b[6] = 0x70 | (rand[0] & 0x0F)  # version 7
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)  # variant 10xx
    b[9:16] = rand[3:10]
    return uuid.UUID(bytes=bytes(b))


def _b32(value: uuid.UUID) -> str:
    n = value.int
    out: list[str] = []
    for _ in range(26):
        out.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(out)).lstrip("0") or "0"


def display_id(prefix: str, value: uuid.UUID) -> str:
    """Support-friendly rendering of a UUID, e.g. ``res_2c8x…``. Not stored; derived."""
    return f"{prefix}_{_b32(value)}"
