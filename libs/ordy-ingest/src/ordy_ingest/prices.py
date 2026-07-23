"""Locale-tolerant price parsing → integer minor units (doc 06 §1).

JSON-LD prices are usually clean ("32.00" or a number), but we defend against
thousands/decimal separator ambiguity. TND uses 3 minor digits.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ordy_core.money import exponent

_NON_NUMERIC = re.compile(r"[^0-9.,]")


def _normalize_decimal(s: str) -> str:
    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        # The rightmost separator is the decimal point; the other groups thousands.
        if s.rfind(",") > s.rfind("."):
            return s.replace(".", "").replace(",", ".")
        return s.replace(",", "")
    if has_comma:
        # Single kind of separator: treat comma as the decimal point.
        return s.replace(",", ".")
    return s


def parse_price(raw: object, currency: str) -> int | None:
    """Return minor units, or None if unparseable."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        dec = Decimal(str(raw))
    else:
        cleaned = _NON_NUMERIC.sub("", str(raw))
        if not cleaned:
            return None
        try:
            dec = Decimal(_normalize_decimal(cleaned))
        except InvalidOperation:
            return None
    factor = Decimal(10) ** exponent(currency)
    return int((dec * factor).to_integral_value(rounding=ROUND_HALF_UP))
