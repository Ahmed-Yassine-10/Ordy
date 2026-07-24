"""Speech + transport ports (doc 05). Vendors plug in behind these; the worker and
pipelines never import a vendor SDK directly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class Transcript:
    text: str
    is_final: bool
    language: str | None = None


class SpeechToText(Protocol):
    """Streaming STT. Yields partial then final transcripts."""

    async def stream(self, audio: AsyncIterator[bytes], *, language: str, boost: list[str]) -> AsyncIterator[Transcript]: ...


class TextToSpeech(Protocol):
    """Streaming TTS. Yields audio chunks for a (possibly partial) text stream."""

    async def synthesize(self, text: AsyncIterator[str], *, voice: str, lexicon: dict[str, str]) -> AsyncIterator[bytes]: ...


class Transport(Protocol):
    """Audio transport (LiveKit room / SIP). Delivers inbound audio, plays outbound."""

    def inbound(self) -> AsyncIterator[bytes]: ...
    async def play(self, audio: AsyncIterator[bytes]) -> None: ...
    async def interrupt(self) -> None: ...  # barge-in: stop playback within ~150ms
