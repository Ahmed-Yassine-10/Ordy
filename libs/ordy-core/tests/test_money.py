"""Money is exponent-aware — TND has 3 minor digits, EUR/USD have 2."""

from __future__ import annotations

import pytest
from ordy_core.money import Money


def test_tnd_formats_with_three_minor_digits() -> None:
    assert Money(32_000, "TND").format() == "32.000 TND"
    assert Money(500, "TND").format() == "0.500 TND"


def test_eur_formats_with_two_minor_digits() -> None:
    assert Money(1_250, "EUR").format() == "12.50 EUR"


def test_addition_requires_matching_currency() -> None:
    assert (Money(1_000, "TND") + Money(500, "TND")).amount_minor == 1_500
    with pytest.raises(ValueError, match="currency mismatch"):
        Money(1_000, "TND") + Money(500, "EUR")


def test_multiplication_by_quantity() -> None:
    assert (Money(32_000, "TND") * 3).format() == "96.000 TND"
