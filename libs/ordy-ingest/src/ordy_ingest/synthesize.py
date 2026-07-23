"""Synthesis stage (doc 04 §2.6): merge per-page extractions into a review-ready
draft bundle, deduping items and computing coverage. Conflicts are flagged, not
silently resolved."""

from __future__ import annotations

from dataclasses import dataclass, field

from ordy_ingest.models import ExtractionResult, HoursDraft, MenuItemDraft, PolicyDraft


@dataclass(slots=True)
class DraftBundle:
    items: list[MenuItemDraft] = field(default_factory=list)
    hours: list[HoursDraft] = field(default_factory=list)
    policies: list[PolicyDraft] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)


def _merge_item(into: MenuItemDraft, other: MenuItemDraft, conflicts: list[dict]) -> None:
    into.description = into.description or other.description
    into.category = into.category or other.category
    into.tags = sorted(set(into.tags) | set(other.tags))
    into.allergens = sorted(set(into.allergens) | set(other.allergens))
    if into.price_minor is None:
        into.price_minor = other.price_minor
    elif other.price_minor is not None and other.price_minor != into.price_minor:
        conflicts.append({
            "kind": "price_conflict",
            "item": into.name,
            "values": [into.price_minor, other.price_minor],
        })
    if not into.variants and other.variants:
        into.variants = other.variants


def synthesize(results: list[ExtractionResult]) -> DraftBundle:
    bundle = DraftBundle()
    by_key: dict[str, MenuItemDraft] = {}

    for res in results:
        for item in res.items:
            existing = by_key.get(item.key())
            if existing is None:
                by_key[item.key()] = item
            else:
                _merge_item(existing, item, bundle.conflicts)
        bundle.hours.extend(res.hours)
        bundle.policies.extend(res.policies)

    bundle.items = list(by_key.values())
    bundle.hours = _dedupe_hours(bundle.hours)
    bundle.policies = _dedupe_policies(bundle.policies)

    categories = {i.category for i in bundle.items if i.category}
    priced = [i for i in bundle.items if i.price_minor is not None or i.variants]
    needing = [i for i in bundle.items if i.needs_review]
    has_allergens = any(i.allergens for i in bundle.items)

    bundle.coverage = {
        "menu_items": len(bundle.items),
        "categories": len(categories),
        "hours": bool(bundle.hours),
        "delivery_policy": any(p.kind == "delivery" for p in bundle.policies),
        "allergens": "partial" if has_allergens else "none",
    }
    bundle.stats = {
        "items_extracted": len(bundle.items),
        "items_priced": len(priced),
        "items_needing_review": len(needing),
        "conflicts": len(bundle.conflicts),
    }
    return bundle


def _dedupe_hours(hours: list[HoursDraft]) -> list[HoursDraft]:
    seen: set[tuple] = set()
    out: list[HoursDraft] = []
    for h in hours:
        sig = (h.service, h.day_of_week, h.opens, h.closes)
        if sig not in seen:
            seen.add(sig)
            out.append(h)
    return out


def _dedupe_policies(policies: list[PolicyDraft]) -> list[PolicyDraft]:
    seen: set[tuple] = set()
    out: list[PolicyDraft] = []
    for p in policies:
        sig = (p.kind, p.text)
        if sig not in seen:
            seen.add(sig)
            out.append(p)
    return out
