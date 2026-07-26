'use strict';
// Human-facing rendering of an analysis run. Kept separate from analysis so the same result
// can be printed, emitted as JSON, or consumed by the Ordy control plane unchanged.

const C = process.stdout.isTTY
  ? { b: '\x1b[1m', dim: '\x1b[2m', g: '\x1b[32m', y: '\x1b[33m', r: '\x1b[31m', c: '\x1b[36m', x: '\x1b[0m' }
  : { b: '', dim: '', g: '', y: '', r: '', c: '', x: '' };

function bar(conf) {
  if (conf >= 0.85) return `${C.g}●${C.x}`;
  if (conf >= 0.75) return `${C.g}◐${C.x}`;
  if (conf > 0) return `${C.y}◔${C.x}`;
  return `${C.dim}○${C.x}`;
}

function renderReport({ info, model, endpoints, capabilities, config }) {
  const L = [];
  L.push(`\n${C.b}Ordy — analyse automatique du projet${C.x}`);
  L.push(`${C.dim}${info.root}${C.x}`);
  L.push('');
  L.push(`  ${C.c}Stack détectée${C.x}   ${info.language} · ${info.framework} · ORM ${info.orm}`);
  L.push(`  ${C.c}Entités${C.x}          ${model.entities.map((e) => e.name).join(', ') || '—'}`);
  L.push(`  ${C.c}Endpoints${C.x}        ${endpoints.length} routes scannées`);
  L.push(
    `  ${C.c}LLM${C.x}              ${config.llm.used ? `${C.g}utilisé${C.x} (${config.llm.model})` : `${C.dim}non utilisé${C.x} — ${config.llm.note}`}`
  );

  L.push(`\n${C.b}  Capability Map${C.x}  ${C.dim}(● sûr  ◐ probable  ◔ à revoir  ○ fallback natif)${C.x}`);
  for (const c of capabilities) {
    const where =
      c.binding === 'rest'
        ? `${c.method} ${c.path} ${C.dim}[${c.auth}]${C.x}`
        : `${C.dim}native${c.reason ? ' — ' + c.reason : ''}${C.x}`;
    const flag = c.needsReview ? ` ${C.y}⚠ à confirmer${C.x}` : '';
    L.push(`   ${bar(c.confidence)} ${c.action.padEnd(24)} ${where}${flag}`);
  }

  const s = config.summary;
  L.push(
    `\n  ${C.b}${s.actionsBoundToApi}${C.x} actions branchées sur l'API · ${s.actionsOnNativeFallback} sur le fallback natif Ordy`
  );
  return L.join('\n');
}

function renderConsent(config, { written, filePath }) {
  const L = [];
  if (config.consent.approved) {
    L.push(`\n${C.g}✓ Consentement enregistré${C.x} — approuvé par ${C.b}${config.consent.approvedBy}${C.x} le ${config.consent.approvedAt}`);
    L.push(`${C.g}✓${C.x} ${filePath} écrit — Ordy est prêt à démarrer avec cette configuration.`);
  } else if (written) {
    L.push(`\n${C.y}Aucune action n'est activée.${C.x} Configuration écrite dans ${filePath} (consentement en attente).`);
    L.push(`Relis la Capability Map ci-dessus, puis approuve :`);
    L.push(`   ${C.b}ordy-analyze --approve "Ton Nom"${C.x}`);
  } else {
    L.push(`\n${C.y}Analyse seule (dry-run).${C.x} Rien n'a été écrit ni activé.`);
    L.push(`Pour générer ordy.config.json : ${C.b}ordy-analyze --write${C.x}`);
    L.push(`Pour approuver directement : ${C.b}ordy-analyze --approve "Ton Nom"${C.x}`);
  }
  return L.join('\n');
}

module.exports = { renderReport, renderConsent };
