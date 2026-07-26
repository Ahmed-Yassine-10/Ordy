# ordy-analyze

**One-command onboarding for Ordy.** A restaurant owner runs a single command in their
existing backend; Ordy reads the project, works out which of its API endpoints map to which
assistant actions, and writes an `ordy.config.json` the owner reviews and approves. No SDK to
wire into the request path, no code sent anywhere.

```bash
npx ordy-analyze                    # analyze the current project (dry run — nothing written)
npx ordy-analyze --write            # emit ordy.config.json (consent still pending)
npx ordy-analyze --approve "Sam"    # analyze + record the owner's consent + write config
```

## How it works

```
detect stack ──▶ read data model (ORM) ──▶ scan API routes ──▶ static capability match
                                                                     │
                                              (ambiguous / missing) ──┴──▶ optional LLM pass
                                                                     │
                                                    ▶ Capability Map ▶ CONSENT GATE ▶ config
```

1. **Detect** — language, framework and ORM from `package.json` + project layout. In a
   monorepo it prefers the manifest that actually declares a server/ORM dependency.
2. **Data model** — parses the Prisma schema (entities, fields, enums). A `Product` with a
   `price`, an `Order` with a `status` are strong signals.
3. **Routes** — resolves every endpoint's `METHOD path [auth]` by reading how routers are
   mounted and what each router declares. Regex-based on purpose: it must run on a stranger's
   repo with nothing installed but Node.
4. **Match** — maps endpoints onto Ordy's fixed action set (`create_order`,
   `check_availability`, …), mirroring the server-side ingester
   (`libs/ordy-ingest/.../analyze.py`). Inbound **webhooks are excluded** — they are
   notifications the restaurant sends Ordy, never actions Ordy calls. Anything not detected
   falls back to Ordy's always-available **native** store, so the assistant works on day one.
5. **Hybrid LLM (optional)** — only the *ambiguous or missing* actions are sent to an LLM, and
   only the public route list + entity **names** go in the prompt — never source code. Enabled
   by setting `ORDY_LLM_KEY` (or `ANTHROPIC_API_KEY`); skipped cleanly otherwise.
6. **Consent** — nothing is activated until a human approves the map. `--approve "Name"`
   records who/when in the config.

## Privacy

Static analysis is fully local; source never leaves the machine. The optional LLM step sees
only what any caller of the API could already see (route list + entity names).

## Output — `ordy.config.json`

A Capability Map: for each action, either a `rest` binding (`method` + `path` + `auth` +
`confidence` + where it was detected) or a `native` fallback, plus the recorded `consent`.
Ordy's control plane consumes this to stand up the assistant against the restaurant's own API.

## Config knobs

| Env | Effect |
|---|---|
| `ORDY_LLM_KEY` / `ANTHROPIC_API_KEY` | enables the hybrid LLM confirmation pass |
| `ORDY_LLM_MODEL` | override the model (default `claude-sonnet-5`) |
| `ORDY_CURRENCY` | currency written to the config (default `TND`) |

## Tests

```bash
node --test tools/ordy-analyze/test/analyze.test.js
```

Covers verb mapping, the webhook-exclusion regression, native fallback, the data-model
confidence boost, the Prisma parser, and an end-to-end run on a synthetic express+prisma
fixture.
