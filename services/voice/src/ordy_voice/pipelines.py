"""Pipeline selection + the two modes (doc 05 §2).

Both modes drive the same agent orchestrator (ordy-agent) — voice is transport, not a
second brain. Mode A = realtime speech-to-speech (EN/FR); Mode B = modular
STT→agent→TTS (required for Derja, and the cost lever). Selection is
(tenant × language × channel); vendor wiring lands after the benchmark spike.
"""

from __future__ import annotations

from enum import StrEnum


class PipelineMode(StrEnum):
    REALTIME = "realtime"  # Mode A — speech-to-speech
    MODULAR = "modular"  # Mode B — STT → agent → TTS


def select_pipeline(
    *, language: str, cost_sensitive: bool = False, realtime_available: bool = True
) -> PipelineMode:
    """Derja always uses the modular pipeline; so do cost-sensitive tenants and the
    realtime-vendor-outage fallback (doc 05 §2 selection matrix)."""
    if str(language).startswith("ar"):
        return PipelineMode.MODULAR
    if cost_sensitive or not realtime_available:
        return PipelineMode.MODULAR
    return PipelineMode.REALTIME
