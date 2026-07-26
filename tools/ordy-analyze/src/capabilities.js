'use strict';
// Capability matcher. Maps detected endpoints onto Ordy's fixed set of platform actions,
// mirroring the heuristics in libs/ordy-ingest/src/ordy_ingest/analyze.py so the CLI and the
// server-side ingester agree. Data-model signals (a Product with a price, an Order with a
// status) nudge confidence. Every action Ordy supports gets an entry: a detected REST
// endpoint upgrades the binding from Ordy's always-available `native` store to `rest`.

const { hasEntity } = require('./prisma');

// Kept in lock-step with analyze.py PLATFORM_ACTIONS.
const PLATFORM_ACTIONS = [
  'create_order',
  'update_order',
  'cancel_order',
  'get_order_status',
  'check_availability',
  'make_reservation',
  'cancel_reservation',
  'check_reservation_slots',
  'request_human_handoff',
  'send_payment_link',
  'log_customer_preference',
];

// These never bind to a restaurant endpoint — they only run against Ordy's own systems.
const ALWAYS_NATIVE = new Set(['request_human_handoff', 'send_payment_link', 'log_customer_preference']);

function matchEndpoint(method, pathStr) {
  const h = `${pathStr} ${method}`.toLowerCase();
  const m = method.toLowerCase();
  const has = (...w) => w.some((x) => h.includes(x));

  const order = has('order');
  const reservation = has('reservation', 'booking', 'reserve', 'table');
  const cancel = has('cancel', 'void');
  const menu = has('product', 'menu', 'item', 'dish', 'catalog', 'plat');
  const availability = has('availab', 'stock', 'inventory');
  const slots = has('slot', 'opening', 'availab');

  if (order && cancel && (m === 'post' || m === 'delete')) return ['cancel_order', 0.85];
  if (order && (m === 'put' || m === 'patch')) return ['update_order', 0.8];
  if (order && m === 'post') return ['create_order', 0.85];
  if (order && m === 'get') return ['get_order_status', 0.75];
  if (reservation && cancel && (m === 'post' || m === 'delete')) return ['cancel_reservation', 0.85];
  if (reservation && slots && m === 'get') return ['check_reservation_slots', 0.8];
  if (reservation && m === 'post') return ['make_reservation', 0.85];
  if (availability && m === 'get') return ['check_availability', 0.8];
  // A plain menu/products listing is Ordy's availability source.
  if (menu && m === 'get') return ['check_availability', 0.7];
  return null;
}

function assembleCapabilityMap(endpoints, model) {
  // Data-model confidence boosts.
  const hasOrder = model && hasEntity(model, /order/i, /status/i);
  const hasPricedProduct = model && hasEntity(model, /product|item|dish|menu/i, /price/i);
  const hasReservation = model && hasEntity(model, /reservation|booking/i);

  // Best endpoint per action.
  const best = {};
  for (const ep of endpoints) {
    // Inbound webhooks/callbacks are notifications the restaurant sends US — never actions
    // Ordy invokes. Excluding them stops an ingest webhook masquerading as create_order.
    if (/webhook|callback|\/hooks?\b/i.test(ep.path)) continue;
    const hit = matchEndpoint(ep.method, ep.path);
    if (!hit) continue;
    let [action, conf] = hit;
    if (action === 'create_order' && hasOrder) conf = Math.min(0.98, conf + 0.1);
    if (action === 'check_availability' && hasPricedProduct) conf = Math.min(0.98, conf + 0.1);
    if ((action === 'make_reservation' || action === 'check_reservation_slots') && hasReservation)
      conf = Math.min(0.98, conf + 0.1);
    const prev = best[action];
    // Higher confidence wins; on a tie, the shorter (more canonical) path wins — so a plain
    // /api/orders beats /api/marketplace/orders/import at equal confidence.
    const better = !prev || conf > prev.confidence || (conf === prev.confidence && ep.path.length < prev.path.length);
    if (better) {
      best[action] = { method: ep.method, path: ep.path, auth: ep.auth, confidence: conf, source: ep.source };
    }
  }

  const REVIEW_THRESHOLD = 0.75;
  const capabilities = PLATFORM_ACTIONS.map((action) => {
    if (ALWAYS_NATIVE.has(action)) {
      return { action, binding: 'native', confidence: 1.0, reason: 'platform-internal action' };
    }
    const found = best[action];
    if (found) {
      return {
        action,
        binding: 'rest',
        method: found.method,
        path: found.path,
        auth: found.auth ? 'bearer' : 'none',
        confidence: Number(found.confidence.toFixed(2)),
        source: 'static',
        needsReview: found.confidence < REVIEW_THRESHOLD,
        detectedIn: found.source,
      };
    }
    // Not detected: Ordy's native store backs order/reservation/availability on day one.
    return { action, binding: 'native', confidence: 0.0, reason: 'no matching endpoint detected' };
  });

  return capabilities;
}

module.exports = { PLATFORM_ACTIONS, ALWAYS_NATIVE, matchEndpoint, assembleCapabilityMap };
