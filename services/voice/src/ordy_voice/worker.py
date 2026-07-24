"""LiveKit agent worker skeleton (doc 05 §1).

A worker joins each room, selects a pipeline, and exchanges turns with the agent
orchestrator over the internal API. The audio loop (VAD/endpointing, barge-in,
streaming STT/TTS) is filled in with the LiveKit Agents framework after the vendor
spike; the control flow is sketched here so the seam is explicit.
"""

from __future__ import annotations

from dataclasses import dataclass

from ordy_voice.pipelines import PipelineMode, select_pipeline


@dataclass(slots=True)
class SessionConfig:
    restaurant_id: str
    language: str
    channel: str  # voice_web | voice_phone
    cost_sensitive: bool = False


class VoiceSession:
    """One audio session. Owns pipeline selection + the turn exchange with the agent."""

    def __init__(self, config: SessionConfig) -> None:
        self.config = config
        self.mode: PipelineMode = select_pipeline(
            language=config.language, cost_sensitive=config.cost_sensitive
        )

    async def run(self) -> None:  # pragma: no cover — needs the audio stack
        raise NotImplementedError(
            "Audio loop is wired with livekit-agents after the Derja STT/TTS spike "
            "(doc 05 §6). Pipeline selection + turn exchange contracts are defined."
        )


async def entrypoint() -> None:  # pragma: no cover
    """LiveKit worker entrypoint — registered with the Agents framework in prod."""
    raise NotImplementedError("register with livekit-agents; see docs/05-voice.md")
