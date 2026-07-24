"""Query rewriting (doc 03 §3.2).

A light, deterministic normalizer plus small FR/EN/Derja synonym expansions for menu
search. Dialogue-aware pronoun resolution ("does IT have meat?") is the LLM's job and
plugs in behind ``QueryRewriter``; the pure path never needs it.
"""

from __future__ import annotations

from typing import Protocol

# Cross-language hints that help lexical recall on small menus.
_EXPANSIONS: dict[str, list[str]] = {
    "vegetarian": ["vegetarian", "végétarien", "sans viande", "veggie"],
    "vegetarien": ["végétarien", "vegetarian", "sans viande"],
    "spicy": ["spicy", "épicé", "harissa", "hot", "حار"],
    "price": ["price", "prix", "cost", "بقداش", "combien"],
    "delivery": ["delivery", "livraison", "توصيل"],
    "halal": ["halal", "حلال"],
}


class QueryRewriter(Protocol):
    def rewrite(self, query: str, *, history: list[str] | None = None) -> str: ...


def rule_rewrite(query: str, *, history: list[str] | None = None) -> str:
    """Normalize whitespace and expand a few known menu terms for recall."""
    normalized = " ".join(query.split())
    lowered = normalized.lower()
    extras: list[str] = []
    for key, synonyms in _EXPANSIONS.items():
        if key in lowered:
            extras.extend(s for s in synonyms if s.lower() not in lowered)
    if extras:
        return f"{normalized} {' '.join(extras)}"
    return normalized
