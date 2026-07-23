# 05 — Voice Architecture

Voice is Ordy's product surface: if the agent is slow, robotic, or can't handle "زيدني بيتزا كبيرة" mid-sentence, nothing else matters. This doc specifies transport, the two speech pipelines, latency budgets, turn-taking, conversation UX, and the language strategy for English, French, and Tunisian Derja.

**Design stance:** voice is a *transport + rendering* layer. Both pipeline modes drive the same agent orchestrator (doc 03) and the same validation/execution pipeline. There is exactly one brain.

## 1. Channels & transport

LiveKit is the single audio backbone (ADR-009):

| Channel | Path | Notes |
|---|---|---|
| **Web widget** | Browser → WebRTC → LiveKit room ← voice worker | Widget requests a session via `POST /v1/public/voice/sessions` → gets LiveKit token; echo cancellation and jitter handled by WebRTC stack |
| **Hosted page** | Same as widget | `order.ordy.ai/{slug}` for restaurants without a website |
| **Phone** | PSTN → Twilio SIP trunk → LiveKit SIP bridge → room ← voice worker | Caller ID → customer lookup; phase 5.5+ |
| **Text fallback** | WS to API (no LiveKit) | Same orchestrator; used by widget text mode and the dashboard sandbox |

A `services/voice` worker joins each room, owning: pipeline selection, STT/TTS vendor sessions, turn-taking, barge-in, latency instrumentation, and turn exchange with the orchestrator (in-process HTTP/gRPC to `services/api`).

## 2. The two pipeline modes

### Mode A — realtime speech-to-speech (EN / FR default)

```
Customer audio ⇄ LiveKit ⇄ voice worker ⇄ realtime speech model (REALTIME_SPEECH tier)
                                                │ function calls
                                                ▼
                                   agent action pipeline (validation → execution)
```

The realtime model handles STT, conversational generation, and TTS natively — lowest latency, natural prosody, native barge-in. **Integration contract:** the realtime session is configured with the tenant's persona prompt and the *same tool manifest* the planner would see; its function calls do not execute anything — they are treated exactly like Planning Agent output and enter the standard validation → confirmation → execution pipeline server-side, with results returned to the session as function outputs. Knowledge queries are exposed to it as a `search_menu` read-tool backed by the RAG pipeline. Mode A collapses the Conversation role into the realtime model; Planning/Validation/Execution remain server-side and unchanged.

### Mode B — modular pipeline (Derja; any language on cost/control grounds)

```
Customer audio → LiveKit → streaming STT (partial + final transcripts)
   → orchestrator turn (full graph, tokens streamed)
   → streaming TTS (sentence-chunked) → LiveKit → customer
```

Full control at every stage: STT vendor per language, TTS voice per persona, and the complete graph (including grounding checks) on every turn. This is the **required** path for Tunisian Derja (§6) and the cost-lever path for high-volume tenants.

### Selection matrix

Per session, chosen by (tenant config × language × channel), stored on the conversation:

| Situation | Mode |
|---|---|
| EN / FR, standard tenant | A |
| Derja detected or configured | B |
| Tenant flagged cost-sensitive | B |
| Realtime vendor outage | B (automatic fallback) |
| Text channels | n/a (direct graph) |

## 3. Latency budget

Target: **≤ 800 ms p50 / ≤ 1500 ms p95** from customer end-of-speech to first agent audio.

Mode B budget (the harder case):

| Stage | Budget (p50) |
|---|---|
| Endpointing decision (VAD + semantic) | 150 ms |
| STT final segment | 150 ms |
| Orchestrator to first token (supervisor + conversation node, prompt-cached) | 250 ms |
| TTS first audio chunk (streaming, first sentence) | 150 ms |
| Transport (LiveKit + network) | 100 ms |

Techniques that make the budget real:

- **Stream everything**: partial STT feeds the supervisor early (intent pre-classification starts before end-of-speech); LLM tokens stream to TTS sentence-by-sentence; TTS streams to the room.
- **Prompt caching**: stable prompt layers (platform + persona + manifest) are cache-hits; only the dynamic tail changes per turn.
- **Acknowledgment covers work**: when a turn triggers planning/validation/execution, the worker immediately speaks a persona-appropriate acknowledgment ("Baheee, نشوفلك…" / "Sure, one moment…") *while* the pipeline runs — perceived latency is the ack latency, not the action latency.
- **Speculative endpointing**: begin the turn on probable end-of-speech; if the customer continues, cancel cheaply (nothing has been spoken yet).
- **No blocking I/O in the hot path**: turn persistence and metering are async write-behind; the checkpoint write is the only sync DB touch.

Every stage emits OTel spans tagged with conversation/turn IDs; the latency dashboard is per-stage, per-language, per-mode.

## 4. Turn-taking & interruptions

- **Endpointing**: VAD (silence threshold tuned per language — French pauses ≠ Derja pauses) + semantic end-of-utterance signal from the STT vendor where available. Config per tenant for noisy counters vs quiet rooms.
- **Barge-in**: customer speech during agent playback → fade out TTS within ~150 ms, truncate the agent turn *in state* at the spoken-word boundary (unspoken text is marked undelivered — the agent must not believe it said things the customer never heard), and route the interruption as a new turn. Mode A: native. Mode B: worker-implemented (playback position tracking).
- **Overlap and back-channels**: short affirmations ("mm", "oui oui") during agent speech are classified as back-channel (no interruption) vs command ("no wait—") by the endpointing layer; threshold errs toward yielding — a waiter who talks over customers loses the table.
- **Silence handling**: no speech 6 s → gentle re-prompt; 15 s more → offer to hold or end; abandoned sessions close cleanly with state persisted (a returning caller within 2 h resumes their cart).

## 5. Conversation UX contract

Behaviors the voice layer guarantees regardless of pipeline:

- **Greeting** — per-tenant, per-language script with dynamic hours awareness ("We're closed now, but I can take an order for tomorrow").
- **Confirmation reads** — validated summaries are spoken *verbatim from the system-generated text* (doc 03 §3.4): items, quantities, total, mode, time. Money is always spoken with currency. The customer's "yes" resumes the interrupt; anything else is treated as an edit, never as consent.
- **Numbers, addresses, phones** — locale-aware rendering for TTS (dinar amounts with millimes only when nonzero; phone numbers digit-grouped; French vs Arabic number phrasing).
- **Repair** — validation rejections arrive as reason codes; the Conversation agent renders them helpfully ("Delivery needs a 25-dinar minimum — you're at 18. Want to add a drink or switch to pickup?").
- **Handoff** — on `request_human_handoff`: live transcript pushed to the dashboard inbox with ring/notification; phone channel can SIP-transfer to the restaurant's line; if no human is available, the agent takes a callback commitment (name + phone captured as a validated action).
- **Degradation** — STT confidence collapsing (noise) → agent asks to repeat once, then offers text mode (widget) or handoff (phone). Model/vendor outage → apology + fallback message with restaurant's phone number. Never dead air: any pipeline stall > 3 s triggers a filler or an honest "one moment".

## 6. Language strategy (EN · FR · Tunisian Derja)

Per-tenant config: enabled languages, default, auto-detect on/off, per-language voice. Detection runs on the first utterance (STT language ID + classifier fallback) and can switch mid-conversation when the customer switches — sticky per turn-run, hysteresis of one turn to avoid flapping on single borrowed words.

**Derja is a first-class requirement and the hardest engineering risk in the voice layer.** Realities the design accounts for:

- **Code-switching is the norm.** Real Tunisian ordering speech mixes Derja, French, and French/Italian menu-item names in one sentence ("نحب نكماندي une pizza quatre fromages كبيرة"). Mode B is mandatory: we need an STT that tolerates mixed Arabic/Latin output, and prompts that instruct the conversation model to accept and produce natural code-switched text.
- **Custom vocabulary is menu-derived.** On publish, each tenant's menu compiles into an STT keyword-boost list and a TTS pronunciation lexicon (item names, "harissa", brand names). This is wired into the pipeline, not an afterthought — item-name recognition accuracy is the single highest-leverage Derja quality factor.
- **Vendor choice is a benchmark, not an assumption.** Phase 5 opens with a spike: a recorded Derja ordering corpus (scripted + volunteer recordings, consented) evaluated across candidate STT vendors/models (Arabic-capable streaming STT and Whisper-family options) on word/item-name accuracy and latency; Arabic TTS candidates rated for naturalness by native speakers. The doc records the decision; config carries it.
- **Fallback ladder** if Derja STT quality is below product bar at launch: (1) understand Derja, reply in Derja-flavored phrasing via best available Arabic TTS; (2) understand Derja, reply in French (socially natural in Tunisia — explicit per-tenant choice); (3) Derja marked beta per tenant until the bar is met. The ladder is a product decision surfaced in the dashboard, not silent degradation.
- **The knowledge layer is language-aware**: menu items carry i18n name fields (doc 06); retrieval queries are rewritten to the menu's canonical language; replies render in the conversation language.

## 7. Voice personality

Per-tenant `agent_configs.voice` (JSONB): pipeline mode overrides, per-language TTS voice IDs, speaking-rate, persona register (formal ↔ street-casual — a specialty coffee bar and a family pizzeria should not sound the same), greeting scripts, filler phrase set per language (fillers are scripted assets, recorded/rendered per voice, not generated per turn — consistency and zero latency).

## 8. Recording, consent, retention

- Configurable per tenant: transcript-only (default) or transcript + audio.
- Audio channel opens with the legally appropriate notice per channel/jurisdiction (phone: recording disclosure line in the greeting; widget: mic-permission screen carries the notice).
- Audio objects: `t/{restaurant_id}/audio/{conversation_id}/…`, encrypted at rest, 30-day default lifecycle (tenant-configurable down to 0), transcript retention per tenant policy; deletion requests cascade (doc 08 §7).
- Voice data never trains models; vendor sessions run with training/data-retention disabled where the vendor offers it — vendor DPA terms are part of the Phase 5 selection criteria.
