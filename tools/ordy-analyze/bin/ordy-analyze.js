#!/usr/bin/env node
'use strict';
// `npx @ordy/analyze` — the whole onboarding, one command.
//
//   ordy-analyze                      analyze the current project (dry run, nothing written)
//   ordy-analyze --write              emit ordy.config.json (consent still pending)
//   ordy-analyze --approve "Name"     analyze + record the owner's consent + write config
//   ordy-analyze --path <dir>         analyze another directory
//   ordy-analyze --json               print the machine-readable config to stdout
//   ordy-analyze --no-llm             skip the hybrid LLM step even if a key is set
//
// The consent gate is deliberate: Ordy never activates against a restaurant's system until a
// human has seen the Capability Map and approved it.

const fs = require('fs');
const path = require('path');
const { analyze } = require('../src/index');
const { renderReport, renderConsent } = require('../src/report');

function parseArgs(argv) {
  const a = { path: process.cwd(), write: false, approve: null, json: false, useLLM: true };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === '--path') a.path = path.resolve(argv[++i]);
    else if (v === '--write') a.write = true;
    else if (v === '--approve') a.approve = argv[++i] || 'owner';
    else if (v === '--json') a.json = true;
    else if (v === '--no-llm') a.useLLM = false;
    else if (v === '--help' || v === '-h') a.help = true;
  }
  return a;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('Usage: ordy-analyze [--path <dir>] [--write] [--approve "Name"] [--json] [--no-llm]');
    return 0;
  }

  const result = await analyze(args.path, { useLLM: args.useLLM });
  const { config } = result;

  if (args.json) {
    if (args.approve) {
      config.consent = { approved: true, approvedBy: args.approve, approvedAt: new Date().toISOString() };
    }
    console.log(JSON.stringify(config, null, 2));
    if (args.write || args.approve) writeConfig(args.path, config);
    return 0;
  }

  console.log(renderReport(result));

  const willWrite = args.write || Boolean(args.approve);
  if (args.approve) {
    config.consent = { approved: true, approvedBy: args.approve, approvedAt: new Date().toISOString() };
  }
  let filePath = path.join(args.path, 'ordy.config.json');
  if (willWrite) filePath = writeConfig(args.path, config);
  console.log(renderConsent(config, { written: willWrite, filePath }));
  return 0;
}

function writeConfig(root, config) {
  const filePath = path.join(root, 'ordy.config.json');
  fs.writeFileSync(filePath, JSON.stringify(config, null, 2) + '\n', 'utf8');
  return filePath;
}

main().then((code) => process.exit(code || 0)).catch((err) => {
  console.error('ordy-analyze failed:', err.message);
  process.exit(1);
});
