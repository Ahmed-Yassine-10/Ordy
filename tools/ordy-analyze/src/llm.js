'use strict';
// Hybrid step: the deterministic matcher runs first and handles the clear cases; the LLM is
// asked ONLY about what's ambiguous (low confidence) or missing (no endpoint detected).
//
// Privacy by design: we never ship source code. The prompt contains only the already-public
// route list (METHOD + path) and entity NAMES — the same surface a caller of the API sees.
// If no key is configured, this is a no-op and the ambiguous items are left for the owner to
// confirm in the consent step. That is the whole point of "static first, LLM to fill gaps".

const { PLATFORM_ACTIONS } = require('./capabilities');

function apiKey() {
  return process.env.ORDY_LLM_KEY || process.env.ANTHROPIC_API_KEY || null;
}

function buildPrompt(endpoints, model, unresolved) {
  const routes = endpoints.map((e) => `${e.method} ${e.path}${e.auth ? ' [auth]' : ''}`).join('\n');
  const entities = (model?.entities || []).map((e) => `${e.name}(${e.fields.map((f) => f.name).join(', ')})`).join('\n');
  return [
    'You map a restaurant backend API onto a FIXED set of assistant actions.',
    `Allowed actions: ${PLATFORM_ACTIONS.join(', ')}.`,
    '',
    'Routes:',
    routes || '(none)',
    '',
    'Entities:',
    entities || '(none)',
    '',
    `For each of these still-unresolved actions, pick the single best route or reply "none": ${unresolved.join(', ')}.`,
    'Respond ONLY as compact JSON: {"action": {"method": "...", "path": "...", "confidence": 0-1} | null, ...}.',
  ].join('\n');
}

/**
 * @returns {Promise<{used: boolean, reason?: string, confirmations: object}>}
 */
async function confirmWithLLM({ endpoints, model, capabilities }) {
  const key = apiKey();
  const unresolved = capabilities
    .filter((c) => c.binding !== 'native' ? c.needsReview : c.confidence === 0 && !isAlwaysNative(c.action))
    .map((c) => c.action)
    .filter((a) => canBindToRest(a));

  if (!key) return { used: false, reason: 'no ORDY_LLM_KEY set — ambiguous items deferred to consent review', confirmations: {} };
  if (unresolved.length === 0) return { used: false, reason: 'nothing ambiguous — static analysis was conclusive', confirmations: {} };
  if (typeof fetch !== 'function') return { used: false, reason: 'fetch unavailable (Node < 18)', confirmations: {} };

  const modelId = process.env.ORDY_LLM_MODEL || 'claude-sonnet-5';
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: modelId,
        max_tokens: 1024,
        messages: [{ role: 'user', content: buildPrompt(endpoints, model, unresolved) }],
      }),
    });
    if (!res.ok) return { used: false, reason: `LLM HTTP ${res.status}`, confirmations: {} };
    const data = await res.json();
    const text = (data.content || []).map((b) => b.text || '').join('');
    const json = text.match(/\{[\s\S]*\}/);
    return { used: true, model: modelId, confirmations: json ? JSON.parse(json[0]) : {} };
  } catch (err) {
    return { used: false, reason: `LLM call failed: ${err.message}`, confirmations: {} };
  }
}

function isAlwaysNative(action) {
  return ['request_human_handoff', 'send_payment_link', 'log_customer_preference'].includes(action);
}
function canBindToRest(action) {
  return !isAlwaysNative(action);
}

/** Fold LLM confirmations back into the capability list (only upgrades, never downgrades). */
function applyConfirmations(capabilities, confirmations) {
  if (!confirmations) return capabilities;
  return capabilities.map((c) => {
    const conf = confirmations[c.action];
    if (!conf || conf === null) return c;
    if (c.binding === 'native' || (conf.confidence || 0) > (c.confidence || 0)) {
      return {
        ...c,
        binding: 'rest',
        method: conf.method,
        path: conf.path,
        confidence: Number(conf.confidence || 0.8),
        source: 'llm',
        needsReview: false,
      };
    }
    return { ...c, needsReview: false, source: c.source === 'static' ? 'static+llm' : c.source };
  });
}

module.exports = { confirmWithLLM, applyConfirmations, apiKey };
