"""Money as integer minor units + ISO-4217 currency. No floats, ever (doc 06 §1).

Note the Tunisian dinar has exponent 3 (1 TND = 1000 millimes), unlike EUR/USD (2).
"""

from __future__ import annotations

from dataclasses import dataclass

# Minor-unit exponents. Extend as markets are added.
_EXPONENTS: dict[str, int] = {
    "TND": 3,
    "EUR": 2,
    "USD": 2,
    "GBP": 2,
}


def exponent(currency: str) -> int:
    return _EXPONENTS.get(currency.upper(), 2)


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be int (minor units)")
        if len(self.currency) != 3:
            raise ValueError(f"currency must be a 3-letter code, got {self.currency!r}")

    @property
    def exponent(self) -> int:
        return exponent(self.currency)

    def _check(self, other: Money) -> None:
        if self.currency.upper() != other.currency.upper():
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __mul__(self, qty: int) -> Money:
        if not isinstance(qty, int):
            raise TypeError("Money can only be multiplied by an int quantity")
        return Money(self.amount_minor * qty, self.currency)

    def format(self) -> str:
        """Human string, e.g. Money(32000, 'TND') -> '32.000 TND'."""
        exp = self.exponent
        if exp == 0:
            return f"{self.amount_minor} {self.currency.upper()}"
        major, minor = divmod(abs(self.amount_minor), 10**exp)
        sign = "-" if self.amount_minor < 0 else ""
        return f"{sign}{major}.{minor:0{exp}d} {self.currency.upper()}"

    def __str__(self) -> str:
        return self.format()
