# services/voice — Voice gateway (Phase 5 scaffold)

LiveKit agent workers that join each audio room and run one of two pipelines, both
driving the same agent orchestrator (`ordy-agent`). See [docs/05-voice.md](../../docs/05-voice.md).

**Landed in Phase 5 (structure, testable):**
- `ports.py` — `SpeechToText` / `TextToSpeech` / `Transport` ports (no vendor SDK leaks into the worker).
- `pipelines.py` — Mode A (realtime) / Mode B (modular) + `select_pipeline` (Derja → modular).
- `lexicon.py` — menu-derived STT keyword boost + TTS pronunciation lexicon (pure).
- `worker.py` — `VoiceSession` skeleton: pipeline selection + the agent turn-exchange seam.

**Pending the Derja STT/TTS benchmark spike (doc 05 §6):** the live audio loop
(VAD/endpointing, barge-in, streaming STT/TTS), LiveKit self-host-vs-cloud decision,
and vendor pinning. None of that runs in the authoring environment; it lands where the
audio toolchain + a recorded Derja corpus are available.
