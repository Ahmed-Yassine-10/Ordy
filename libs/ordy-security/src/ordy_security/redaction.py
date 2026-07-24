"""PII + secret redaction at the logging/tracing boundary (doc 08 §7).

Everything leaving the process — logs, traces, error payloads, artifacts — passes through
here. This is a backstop, not a substitute for not collecting the data: the point is that
a stray `logger.info(request_body)` cannot leak a phone number or an API key.
"""

from __future__ import annotations

import re

REDACTED = "[redacted]"

# Ordered: more specific patterns first so a card number isn't caught as a phone.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("api_key", re.compile(r"\bordy_(?:live|test)_[A-Za-z0-9_-]{8,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("phone", re.compile(r"\+\d[\d\s().-]{6,}\d")),
)

# Dict keys whose VALUE is always secret regardless of shape.
_SECRET_KEYS = (
    "password", "passwd", "secret", "token", "authorization", "api_key", "apikey",
    "access_token", "refresh_token", "private_key", "card_number", "cvv", "cvc",
    "secret_enc", "key_hash", "mfa_secret", "connection_string", "dsn",
)


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "_", str(key).lower())
    return any(marker in normalized for marker in _SECRET_KEYS)


def redact_text(text: str) -> str:
    """Mask PII/secret-shaped substrings in free text."""
    if not text:
        return text
    out = text
    for _, pattern in _PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def redact(value: object, *, _depth: int = 0) -> object:
    """Recursively redact a log record / trace attribute / error payload.

    Key-based redaction wins over shape-based: a value under `password` is masked even if
    it looks harmless.
    """
    if _depth > 8:
        return "[truncated]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: (REDACTED if _is_secret_key(key) else redact(item, _depth=_depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth=_depth + 1) for item in value]
    return value


def safe_phone(phone: str | None) -> str:
    """Last-4 rendering for operational UIs that legitimately need to identify a caller."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return f"***{digits[-4:]}" if len(digits) >= 4 else REDACTED
