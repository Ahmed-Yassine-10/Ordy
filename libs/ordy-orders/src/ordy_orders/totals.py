"""Order totals + promotions (doc 06 §3.2/§3.3).

All arithmetic in integer minor units — no floats touch money. Discounts are clamped so
a promotion can never produce a negative total (a classic injected-discount failure).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OrderTotals:
    subtotal_minor: int
    delivery_fee_minor: int = 0
    discount_minor: int = 0

    @property
    def total_minor(self) -> int:
        return max(0, self.subtotal_minor - self.discount_minor) + self.delivery_fee_minor


def apply_promotion(subtotal_minor: int, rule: dict | None) -> int:
    """Return the discount in minor units. Unknown/invalid rules discount nothing."""
    if not rule:
        return 0
    conditions = rule.get("conditions") or {}
    if subtotal_minor < int(conditions.get("min_order_minor", 0)):
        return 0

    kind = rule.get("type")
    value = rule.get("value", 0)
    if kind == "percent":
        percent = max(0, min(100, int(value)))
        discount = subtotal_minor * percent // 100
    elif kind == "amount":
        discount = max(0, int(value))
    else:
        return 0
    return min(discount, subtotal_minor)  # never exceeds the subtotal


def compute_totals(
    subtotal_minor: int, *, delivery_fee_minor: int = 0, promotion: dict | None = None
) -> OrderTotals:
    return OrderTotals(
        subtotal_minor=subtotal_minor,
        delivery_fee_minor=delivery_fee_minor,
        discount_minor=apply_promotion(subtotal_minor, promotion),
    )
