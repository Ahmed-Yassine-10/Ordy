# Phase 5 — Conversational agent (read-only)

Status of the Phase 5 build (roadmap [doc 10](10-roadmap.md)). Goal: talk to the agent
about the menu, hours, and policies — grounded in approved knowledge — over the text
sandbox, with the voice transport scaffolded behind ports. **Read-only**: tool calling
and order execution are Phases 6–7.

## What's implemented

**`libs/ordy-agent`** — the brain, pure over its ports so a full turn runs without a
provider or a DB:
- **`state.py`**: typed `ConversationState` (turns, intent, retrieval context, status).
- **`brain.py`**: the `AgentBrain` port with a deterministic **`RuleBasedBrain`**
  (dev/CI/evals — reproducible) and an **`LLMBrain`** (prod) that maps each role
  operation to a model-router tier + prompt.
- **`router.py`**: the `ModelRouter` — named tiers → model IDs, per-tenant overridable
  (no model ID in node logic, ADR-008).
- **`engine.py`**: the turn engine — supervisor routing (→ knowledge / conversation /
  handoff), retrieval via an injected retriever, and **grounding enforced in code**
  regardless of the brain (an ungrounded price never reaches the customer).
- **`graph.py`**: the LangGraph assembly (ADR-004) — primary from Phase 6, when
  Planning/Validation/Execution + the confirmation interrupt need durable checkpointing.
- **`prompts.py`**: layered, injection-quarantined prompts (retrieved content is data,
  not instructions — doc 08 §6.1).

**Data**: migration `0004` adds `agent_configs`, `conversations`, `conversation_turns`
under the same FORCE'd per-tenant RLS.

**`services/api`** — the agent module:
- `GET/PATCH /agent-config` (persona, voice, languages, escalation).
- `POST /sandbox/conversations` + `POST /sandbox/conversations/{id}/turns` — runs the
  full read-only turn against **live approved knowledge**, persists every turn with its
  trace (route + retrieval + grounding), forces text mode.
- `GET /conversations/{id}` — transcript with per-turn latency (playback foundation).
- Retriever adapter binds the agent to pgvector hybrid search on the RLS-scoped session.

**`services/voice`** — scaffold behind ports: `SpeechToText`/`TextToSpeech`/`Transport`
ports, Mode A/B `select_pipeline` (Derja → modular), the pure **menu-derived lexicon
compiler** (STT boost + TTS pronunciation), and the `VoiceSession` worker skeleton.

**Frontend**: a text **sandbox chat** — talk to the agent, each reply badged with its
route, a grounded/ungrounded indicator, and a click-through to the source.

## Validation done in this environment

The **full agent turn runs here** (Python 3.13, stdlib) — 5 golden-conversation tests +
2 voice-scaffold tests pass: greeting → persona reply; "how much is the pepperoni
pizza?" → knowledge route, **grounded**, reply contains `32000`, provenance attached;
vegetarian → Margherita; "talk to a human" → handoff + escalated; multi-turn state
accumulation; Derja → modular pipeline; lexicon boosts item names + Tunisian terms.
**22 unit tests pass across the repo.** All Python compiles.

The DB-bound sandbox (conversation persistence, retriever over pgvector) and the entire
audio path are syntax-validated but **not executed** here — no Postgres/LiveKit/STT in
the authoring env. CI + `docker compose` are the reference; the voice audio loop lands
after the Derja spike.

## Remaining / deferred

- LLM brain implementation (model-router completion client) — `RuleBasedBrain` backs dev/CI.
- **Voice audio loop** (LiveKit rooms, VAD/endpointing, barge-in, streaming STT/TTS) +
  the **Derja STT/TTS benchmark spike** (doc 05 §6) — the phase's biggest external
  dependency, deferred to where the toolchain + a recorded corpus exist.
- Latency instrumentation dashboard (≤ 800 ms p50 voice-to-voice target).
- Conversation audio playback (transcripts persist now; audio arrives with the audio loop).
