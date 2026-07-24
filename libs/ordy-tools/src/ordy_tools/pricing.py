"""Server-side pricing (doc 03 §3.4).

The model picks items; **the system prices them**. Any price or total present in model
output is discarded — totals here are computed only from the menu snapshot. This is the
single most important defense against a hallucinated or injected discount.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ordy_core.money import exponent

from ordy_tools.models import (
    PRODUCT_NOT_FOUND,
    PRODUCT_UNAVAILABLE,
    VARIANT_REQUIRED,
)


@dataclass(slots=True)
class VariantSnapshot:
    variant_id: str
    name: str
    price_minor: int
    is_available: bool = True


@dataclass(slots=True)
class ProductSnapshot:
    product_id: str
    name: str
    currency: str
    price_minor: int | None = None
    is_available: bool = True
    variants: dict[str, VariantSnapshot] = field(default_factory=dict)


@dataclass(slots=True)
class PricedItem:
    product_id: str
    name: str
    quantity: int
    unit_price_minor: int
    total_minor: int
    variant_id: str | None = None
    variant_name: str | None = None

    def label(self) -> str:
        base = f"{self.quantity}× {self.name}"
        return f"{base} ({self.variant_name})" if self.variant_name else base


@dataclass(slots=True)
class PricingResult:
    items: list[PricedItem] = field(default_factory=list)
    total_minor: int = 0
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


def price_items(items: list[dict], menu: dict[str, ProductSnapshot]) -> PricingResult:
    """Resolve each requested item against the menu snapshot and compute the total."""
    result = PricingResult()
    for raw in items:
        product_id = str(raw.get("product_id", ""))
        product = menu.get(product_id)
        if product is None:
            return PricingResult(
                error_code=PRODUCT_NOT_FOUND,
                error_message=f"We don't have that item on the menu (id {product_id[:8]}…).",
            )
        if not product.is_available:
            return PricingResult(
                error_code=PRODUCT_UNAVAILABLE,
                error_message=f"Sorry, {product.name} isn't available right now.",
            )

        quantity = int(raw.get("quantity", 1))
        variant_id = raw.get("variant_id")
        variant: VariantSnapshot | None = None

        if product.variants:
            if not variant_id:
                options = ", ".join(v.name for v in product.variants.values())
                return PricingResult(
                    error_code=VARIANT_REQUIRED,
                    error_message=f"Which size for {product.name}? We have {options}.",
                )
            variant = product.variants.get(str(variant_id))
            if variant is None:
                return PricingResult(
                    error_code=PRODUCT_NOT_FOUND,
                    error_message=f"That option isn't available for {product.name}.",
                )
            if not variant.is_available:
                return PricingResult(
                    error_code=PRODUCT_UNAVAILABLE,
                    error_message=f"{product.name} ({variant.name}) is sold out right now.",
                )

        unit_price = variant.price_minor if variant else product.price_minor
        if unit_price is None:
            return PricingResult(
                error_code=VARIANT_REQUIRED,
                error_message=f"{product.name} needs an option selected before I can price it.",
            )

        priced = PricedItem(
            product_id=product_id,
            name=product.name,
            quantity=quantity,
            unit_price_minor=unit_price,
            total_minor=unit_price * quantity,
            variant_id=variant.variant_id if variant else None,
            variant_name=variant.name if variant else None,
        )
        result.items.append(priced)
        result.total_minor += priced.total_minor
    return result


def format_money(amount_minor: int, currency: str) -> str:
    exp = exponent(currency)
    if exp == 0:
        return f"{amount_minor} {currency}"
    return f"{amount_minor / (10 ** exp):.{exp}f} {currency}"
