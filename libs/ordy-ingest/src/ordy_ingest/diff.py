"""Change detection for continuous monitoring (doc 04 §2.9).

Price/availability changes are *substantive* → they always route back to human
review (ADR-012). Cosmetic changes can auto-approve.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ordy_ingest.models import MenuItemDraft


def content_hash(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


@dataclass(slots=True)
class Change:
    kind: str  # added | removed | price_changed
    name: str
    old: int | None = None
    new: int | None = None

    @property
    def requires_review(self) -> bool:
        # Price changes and removals must be seen by a human before going live.
        return self.kind in {"price_changed", "removed"}


def _price_of(item: MenuItemDraft) -> int | None:
    if item.price_minor is not None:
        return item.price_minor
    if item.variants:
        return min(v.price_minor for v in item.variants)
    return None


def detect_menu_changes(
    old_items: list[MenuItemDraft], new_items: list[MenuItemDraft]
) -> list[Change]:
    old_map = {i.key(): _price_of(i) for i in old_items}
    new_map = {i.key(): _price_of(i) for i in new_items}
    changes: list[Change] = []

    for key, new_price in new_map.items():
        if key not in old_map:
            changes.append(Change(kind="added", name=key, new=new_price))
        elif old_map[key] != new_price:
            changes.append(Change(kind="price_changed", name=key, old=old_map[key], new=new_price))
    for key, old_price in old_map.items():
        if key not in new_map:
            changes.append(Change(kind="removed", name=key, old=old_price))
    return changes
