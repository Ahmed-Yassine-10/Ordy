"""Sandbox safety guards (doc 08 §5, ADR-011).

Two hard rules, enforced in the runner itself rather than trusted to the workflow:

1. **Egress allowlist** — a run may only reach the approved target domain over http(s).
   Private ranges, loopback, link-local, and cloud metadata endpoints are refused even if
   a workflow (or a redirect) names them. This is the SSRF boundary.
2. **Never fill payment credentials** — the agent never types a card number, CVV, or
   password. Refusal happens before the value reaches the browser, so a tampered or
   drifted workflow cannot smuggle it through.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# Cloud metadata + well-known internal names. Blocked regardless of allowlist.
BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",  # noqa: S104 — this is a denylist entry, not a bind address
}

# Field names we refuse to fill, matched loosely (normalized, substring).
NEVER_FILL_PATTERNS = (
    "card_number", "cardnumber", "cardnum", "cc_number", "ccnumber", "cc-number",
    "cvv", "cvc", "csc", "security_code", "securitycode",
    "password", "passwd", "pin", "iban", "routing_number", "sort_code",
)

# Characters that could break out of a CSS/text selector if interpolated raw.
_SELECTOR_UNSAFE = re.compile(r"""["'\[\]<>(){}\\;]""")


class EgressBlocked(PermissionError):
    """Raised when a run tries to reach a host outside the approved allowlist."""


class PaymentFieldRefused(PermissionError):
    """Raised when a workflow tries to fill a payment/credential field."""


def _host_is_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _domain_allowed(host: str, allowlist: set[str]) -> bool:
    host = host.lower().rstrip(".")
    for allowed in allowlist:
        allowed = allowed.lower().rstrip(".")
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def is_egress_allowed(url: str, allowlist: set[str]) -> bool:
    """True only for http(s) URLs on an allow-listed public host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False  # file://, data://, chrome:// … never
    host = (parsed.hostname or "").lower()
    if not host or host in BLOCKED_HOSTS:
        return False

    ip = _host_is_ip_literal(host)
    if ip is not None:
        # Never allow raw IPs into private/loopback/link-local/reserved space.
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return _domain_allowed(host, allowlist)


def assert_egress_allowed(url: str, allowlist: set[str]) -> None:
    if not is_egress_allowed(url, allowlist):
        raise EgressBlocked(f"egress to '{url}' is not permitted")


def _normalize_field(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def is_never_fill(field_name: str, extra: list[str] | None = None) -> bool:
    normalized = _normalize_field(field_name)
    patterns = list(NEVER_FILL_PATTERNS) + [_normalize_field(e) for e in (extra or [])]
    return any(pattern in normalized for pattern in patterns)


def assert_fields_safe(fields: dict[str, str], extra: list[str] | None = None) -> None:
    """Refuse the whole step if ANY field looks like a payment credential."""
    for name in fields:
        if is_never_fill(name, extra):
            raise PaymentFieldRefused(
                f"refusing to fill '{name}' — Ordy never enters payment or credential data"
            )


def sanitize_for_selector(value: str) -> str:
    """Parameter values are DATA. Strip characters that could restructure a selector."""
    return _SELECTOR_UNSAFE.sub("", value).strip()


def mask_for_artifact(field_name: str, value: str) -> str:
    """Screenshots/DOM snapshots must never carry secrets (doc 08 §4)."""
    if is_never_fill(field_name):
        return "***"
    if len(value) > 4 and any(ch.isdigit() for ch in value):
        return f"{value[:2]}***{value[-2:]}"
    return value
