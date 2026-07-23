"""Extraction stage (doc 04 §2.4).

The default, dependency-free extractor reads schema.org JSON-LD (``Menu`` /
``MenuSection`` / ``MenuItem`` / ``Restaurant``), which a large share of restaurant
sites and site builders emit. An optional LLM extractor (behind ``LLMExtractor``)
fills gaps for sites without structured data; it is never trusted to price items —
prices are re-derived at publish from the reviewed drafts (doc 03 §3.4).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from ordy_ingest.models import (
    ExtractionResult,
    HoursDraft,
    MenuItemDraft,
    PolicyDraft,
    Provenance,
    VariantDraft,
)
from ordy_ingest.prices import parse_price

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_DAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


class LLMExtractor(Protocol):
    """Provider-agnostic structured extractor (ADR-008). Implemented in Phase 3.x
    against the model router; the pure pipeline works without it."""

    def extract(self, *, text: str, url: str, currency: str) -> ExtractionResult: ...


class NullLLMExtractor:
    """No-op extractor used when no LLM is configured (dev / tests)."""

    def extract(self, *, text: str, url: str, currency: str) -> ExtractionResult:
        return ExtractionResult()


def _types(node: dict) -> set[str]:
    raw = node.get("@type", [])
    values = raw if isinstance(raw, list) else [raw]
    out: set[str] = set()
    for v in values:
        if isinstance(v, str):
            out.add(v.rsplit("/", 1)[-1].lower())
    return out


def _find_blocks(html: str) -> list[object]:
    blocks: list[object] = []
    for match in _JSONLD_RE.findall(html):
        try:
            blocks.append(json.loads(match.strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    return blocks


def _offers(node: dict) -> list[tuple[str | None, object, str | None]]:
    """Return list of (name, price, currency) from a node's offers/priceSpecification."""
    result: list[tuple[str | None, object, str | None]] = []
    offers = node.get("offers")
    candidates = offers if isinstance(offers, list) else [offers] if offers else []
    for offer in candidates:
        if not isinstance(offer, dict):
            continue
        spec = offer.get("priceSpecification")
        if isinstance(spec, dict):
            result.append((offer.get("name"), spec.get("price"), spec.get("priceCurrency")))
        else:
            result.append((offer.get("name"), offer.get("price"), offer.get("priceCurrency")))
    return result


def _menu_item(node: dict, *, category: str | None, url: str, default_currency: str) -> MenuItemDraft:
    name = str(node.get("name", "")).strip()
    offers = _offers(node)
    currency = default_currency
    for _, _, cur in offers:
        if cur:
            currency = str(cur)
            break

    price_minor: int | None = None
    variants: list[VariantDraft] = []
    if len(offers) == 1:
        price_minor = parse_price(offers[0][1], currency)
    elif len(offers) > 1:
        for idx, (oname, oprice, _) in enumerate(offers):
            pm = parse_price(oprice, currency)
            if pm is not None:
                variants.append(VariantDraft(name=str(oname) if oname else f"Option {idx + 1}", price_minor=pm))

    suitable = node.get("suitableForDiet") or []
    tags = [str(d).rsplit("/", 1)[-1] for d in (suitable if isinstance(suitable, list) else [suitable])]

    return MenuItemDraft(
        name=name,
        currency=currency,
        description=(str(node["description"]).strip() if node.get("description") else None),
        category=category,
        price_minor=price_minor,
        variants=variants,
        tags=[t for t in tags if t],
        confidence=0.9,
        provenance=Provenance(source_url=url, method="json-ld", snippet=name),
        needs_review=(price_minor is None and not variants),
    )


def _hours(node: dict, url: str) -> list[HoursDraft]:
    spec = node.get("openingHoursSpecification")
    if not spec:
        return []
    specs = spec if isinstance(spec, list) else [spec]
    out: list[HoursDraft] = []
    for s in specs:
        if not isinstance(s, dict):
            continue
        opens, closes = s.get("opens"), s.get("closes")
        if not (opens and closes):
            continue
        days = s.get("dayOfWeek", [])
        days = days if isinstance(days, list) else [days]
        for d in days:
            key = str(d).rsplit("/", 1)[-1].lower()
            if key in _DAYS:
                out.append(
                    HoursDraft(
                        service="dine_in",
                        day_of_week=_DAYS[key],
                        opens=str(opens)[:5],
                        closes=str(closes)[:5],
                        provenance=Provenance(source_url=url, method="json-ld"),
                    )
                )
    return out


def _walk(node: object, *, category: str | None, url: str, currency: str, result: ExtractionResult) -> None:
    if isinstance(node, list):
        for child in node:
            _walk(child, category=category, url=url, currency=currency, result=result)
        return
    if not isinstance(node, dict):
        return

    types = _types(node)
    if "menuitem" in types:
        item = _menu_item(node, category=category, url=url, default_currency=currency)
        if item.name:
            result.items.append(item)
        return

    next_category = category
    if "menusection" in types and node.get("name"):
        next_category = str(node["name"]).strip()

    if types & {"restaurant", "foodestablishment", "cafeorcoffeeshop"}:
        result.hours.extend(_hours(node, url))

    # Recurse into known containers and @graph; also generic dict values.
    for key in ("@graph", "hasMenu", "hasMenuSection", "hasMenuItem", "menu", "itemListElement"):
        if key in node:
            _walk(node[key], category=next_category, url=url, currency=currency, result=result)
    for key, value in node.items():
        if key in {"@graph", "hasMenu", "hasMenuSection", "hasMenuItem", "menu", "itemListElement"}:
            continue
        if isinstance(value, (list, dict)):
            _walk(value, category=next_category, url=url, currency=currency, result=result)


def extract_jsonld(page, default_currency: str) -> ExtractionResult:  # type: ignore[no-untyped-def]
    """Extract menu items, hours (and, later, policies) from a page's JSON-LD."""
    result = ExtractionResult()
    for block in _find_blocks(page.html):
        _walk(block, category=None, url=page.url, currency=default_currency, result=result)
    # Dedupe items within a page by (name, category).
    seen: set[tuple[str, str | None]] = set()
    deduped: list[MenuItemDraft] = []
    for item in result.items:
        sig = (item.key(), item.category)
        if sig not in seen:
            seen.add(sig)
            deduped.append(item)
    result.items = deduped
    return result


def note_policies_from_text(text: str, url: str) -> list[PolicyDraft]:
    """Very light policy sniffing used as a fallback signal for the reviewer."""
    policies: list[PolicyDraft] = []
    lowered = text.lower()
    if "livraison" in lowered or "delivery" in lowered:
        policies.append(PolicyDraft(kind="delivery", text="Delivery mentioned on page",
                                    provenance=Provenance(source_url=url, method="heuristic")))
    return policies
