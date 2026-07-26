'use strict';
// Orchestrates one analysis run: detect → data model → routes → static match → hybrid LLM
// → assembled Ordy config. Pure with respect to the filesystem output (the caller decides
// whether to write ordy.config.json), so it's easy to test and to embed elsewhere.

const { detect } = require('./detect');
const { parsePrismaSchema } = require('./prisma');
const { scanRoutes } = require('./routes');
const { assembleCapabilityMap } = require('./capabilities');
const { confirmWithLLM, applyConfirmations } = require('./llm');

async function analyze(root, { useLLM = true } = {}) {
  const info = detect(root);
  const model = info.files.prismaSchema ? parsePrismaSchema(info.files.prismaSchema) : { entities: [], enums: [] };
  const endpoints = scanRoutes(info);

  let capabilities = assembleCapabilityMap(endpoints, model);

  let llm = { used: false, reason: 'LLM step disabled', confirmations: {} };
  if (useLLM) {
    llm = await confirmWithLLM({ endpoints, model, capabilities });
    if (llm.used) capabilities = applyConfirmations(capabilities, llm.confirmations);
  }

  const bound = capabilities.filter((c) => c.binding === 'rest').length;
  const config = {
    ordyVersion: '0.1',
    generatedBy: '@ordy/analyze',
    restaurant: {
      // Sub-package names like "backend"/"api"/"server" aren't the restaurant's name; fall
      // back to the project folder in that case.
      name: /^(backend|api|server|app|src)$/i.test(info.packageName || '')
        ? require('path').basename(root)
        : info.packageName || require('path').basename(root),
      currency: info.currency,
    },
    detected: {
      language: info.language,
      framework: info.framework,
      orm: info.orm,
      apiBasePath: info.apiBasePath,
      entities: model.entities.map((e) => e.name),
    },
    auth: inferAuth(endpoints),
    capabilities,
    llm: { used: llm.used, model: llm.model || null, note: llm.reason || null },
    consent: { approved: false, approvedBy: null, approvedAt: null },
    summary: {
      endpointsScanned: endpoints.length,
      actionsBoundToApi: bound,
      actionsOnNativeFallback: capabilities.length - bound,
    },
  };
  return { info, model, endpoints, capabilities, config };
}

function inferAuth(endpoints) {
  const anyAuth = endpoints.some((e) => e.auth);
  return { scheme: anyAuth ? 'bearer' : 'none', tokenEnv: 'ORDY_RESTAURANT_TOKEN' };
}

module.exports = { analyze };
