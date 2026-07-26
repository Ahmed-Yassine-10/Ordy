'use strict';
// Run with:  node --test tools/ordy-analyze/test/
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { matchEndpoint, assembleCapabilityMap } = require('../src/capabilities');
const { parsePrismaSchema } = require('../src/prisma');
const { analyze } = require('../src/index');

test('matchEndpoint maps the core CRUD verbs', () => {
  assert.deepEqual(matchEndpoint('POST', '/api/orders')[0], 'create_order');
  assert.deepEqual(matchEndpoint('GET', '/api/orders/:id')[0], 'get_order_status');
  assert.deepEqual(matchEndpoint('PATCH', '/api/orders/:id/status')[0], 'update_order');
  assert.deepEqual(matchEndpoint('GET', '/api/products')[0], 'check_availability');
  assert.deepEqual(matchEndpoint('POST', '/api/reservations')[0], 'make_reservation');
  assert.equal(matchEndpoint('GET', '/api/health'), null);
});

test('inbound webhooks never bind as create_order (regression)', () => {
  const endpoints = [
    { method: 'POST', path: '/api/webhooks/glovo/orders', auth: false, source: 'app.ts' },
    { method: 'POST', path: '/api/orders', auth: true, source: 'orderRoutes.ts' },
  ];
  const model = { entities: [{ name: 'Order', fields: [{ name: 'status' }] }] };
  const caps = assembleCapabilityMap(endpoints, model);
  const create = caps.find((c) => c.action === 'create_order');
  assert.equal(create.path, '/api/orders', 'must pick the real endpoint, not the ingest webhook');
  assert.equal(create.binding, 'rest');
});

test('undetected actions fall back to native; platform actions are always native', () => {
  const caps = assembleCapabilityMap([], { entities: [] });
  const reservation = caps.find((c) => c.action === 'make_reservation');
  assert.equal(reservation.binding, 'native');
  const handoff = caps.find((c) => c.action === 'request_human_handoff');
  assert.equal(handoff.binding, 'native');
  assert.equal(handoff.confidence, 1);
});

test('data-model signal boosts confidence and shorter path wins ties', () => {
  const endpoints = [
    { method: 'POST', path: '/api/marketplace/orders/import', auth: true, source: 'm.ts' },
    { method: 'POST', path: '/api/orders', auth: true, source: 'o.ts' },
  ];
  const withStatus = assembleCapabilityMap(endpoints, {
    entities: [{ name: 'Order', fields: [{ name: 'status' }] }],
  });
  const c = withStatus.find((x) => x.action === 'create_order');
  assert.equal(c.path, '/api/orders');
  assert.ok(c.confidence >= 0.95, 'Order.status should boost create_order confidence');
});

test('prisma parser extracts entities, fields and enums', () => {
  const schema = `
    enum OrderStatus { PENDING PREPARING READY }
    model Product {
      id String @id
      name String
      price Float
      isAvailable Boolean @default(true)
    }
    model Order {
      id String @id
      status OrderStatus @default(PENDING)
    }`;
  const tmp = path.join(os.tmpdir(), `ordy-schema-${process.pid}.prisma`);
  fs.writeFileSync(tmp, schema);
  const model = parsePrismaSchema(tmp);
  fs.unlinkSync(tmp);

  assert.deepEqual(model.entities.map((e) => e.name).sort(), ['Order', 'Product']);
  const product = model.entities.find((e) => e.name === 'Product');
  assert.ok(product.fields.some((f) => f.name === 'price' && f.type === 'Float'));
  assert.deepEqual(model.enums[0], { name: 'OrderStatus', values: ['PENDING', 'PREPARING', 'READY'] });
});

test('analyze() end-to-end on a tiny express+prisma fixture', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ordy-fix-'));
  fs.mkdirSync(path.join(dir, 'prisma'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'src', 'routes'), { recursive: true });
  fs.writeFileSync(
    path.join(dir, 'package.json'),
    JSON.stringify({ name: 'demo', dependencies: { express: '^5', '@prisma/client': '^5' } })
  );
  fs.writeFileSync(
    path.join(dir, 'prisma', 'schema.prisma'),
    'model Product { id String @id\n price Float\n isAvailable Boolean }\nmodel Order { id String @id\n status String }'
  );
  fs.writeFileSync(
    path.join(dir, 'src', 'app.ts'),
    "import orderRoutes from './routes/orderRoutes';\nimport productRoutes from './routes/productRoutes';\n" +
      "const app = express();\napp.use('/api/orders', orderRoutes);\napp.use('/api/products', productRoutes);\n"
  );
  fs.writeFileSync(
    path.join(dir, 'src', 'routes', 'orderRoutes.ts'),
    "const router = Router();\nrouter.post('/', authenticate, createOrder);\nexport default router;"
  );
  fs.writeFileSync(
    path.join(dir, 'src', 'routes', 'productRoutes.ts'),
    "const router = Router();\nrouter.get('/', getProducts);\nexport default router;"
  );

  const { config } = await analyze(dir, { useLLM: false });
  assert.equal(config.detected.framework, 'express');
  assert.equal(config.detected.orm, 'prisma');
  const create = config.capabilities.find((c) => c.action === 'create_order');
  assert.equal(create.binding, 'rest');
  assert.equal(create.path, '/api/orders');
  assert.equal(create.auth, 'bearer');
  const menu = config.capabilities.find((c) => c.action === 'check_availability');
  assert.equal(menu.path, '/api/products');

  fs.rmSync(dir, { recursive: true, force: true });
});
