"""Grounding-check plumbing (doc 03 §3.2, §7).

A cheap heuristic baseline: every price-like number the agent says must appear in the
retrieved context. Ungrounded numbers are the highest-risk hallucination for a voice
agent quoting prices. A stronger LLM-judge grounding pass plugs in later behind the
same report shape; the deterministic check always runs first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ordy_rag.models import RetrievedChunk

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass(slots=True)
class GroundingReport:
    grounded: bool
    unsupported_numbers: list[str] = field(default_factory=list)

    @property
    def should_regenerate(self) -> bool:
        return not self.grounded


def _numbers(text: str) -> set[str]:
    # Normalize separators so "32.000" and "32,000" compare equal.
    return {m.replace(",", ".") for m in _NUMBER_RE.findall(text)}


def check_grounding(reply: str, chunks: list[RetrievedChunk]) -> GroundingReport:
    context_numbers = set()
    for chunk in chunks:
        context_numbers |= _numbers(chunk.content)
    unsupported = sorted(n for n in _numbers(reply) if n not in context_numbers)
    return GroundingReport(grounded=not unsupported, unsupported_numbers=unsupported)
