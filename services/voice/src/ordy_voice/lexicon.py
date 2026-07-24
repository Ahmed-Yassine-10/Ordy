"""Menu-derived STT keyword boost + TTS pronunciation lexicon (doc 05 §6).

Compiled on publish; item-name recognition accuracy is the single highest-leverage
Derja quality lever. Pure + testable — no audio stack needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Terms worth boosting regardless of menu (Tunisian food vocabulary + brands).
_BASE_TERMS = ["harissa", "brik", "makloub", "lablabi", "mlawi", "chapati", "kafteji"]

_STOPWORDS = {"the", "and", "with", "de", "la", "le", "les", "et", "au", "aux", "du"}


@dataclass(slots=True)
class Lexicon:
    boost: list[str] = field(default_factory=list)  # STT keyword boost list
    pronunciations: dict[str, str] = field(default_factory=dict)  # TTS lexicon (term -> hint)


def _terms_from_name(name: str) -> list[str]:
    words = re.findall(r"[A-Za-z؀-ۿ]+", name)
    return [w for w in words if len(w) > 2 and w.lower() not in _STOPWORDS]


def compile_lexicon(item_names: list[str], *, pronunciations: dict[str, str] | None = None) -> Lexicon:
    """Build the boost list (full item names + salient words + base terms) and the TTS
    pronunciation map from a restaurant's menu."""
    boost: list[str] = []
    seen: set[str] = set()

    def _add(term: str) -> None:
        key = term.lower().strip()
        if key and key not in seen:
            seen.add(key)
            boost.append(term.strip())

    for name in item_names:
        _add(name)
        for word in _terms_from_name(name):
            _add(word)
    for term in _BASE_TERMS:
        _add(term)

    return Lexicon(boost=boost, pronunciations=dict(pronunciations or {}))
