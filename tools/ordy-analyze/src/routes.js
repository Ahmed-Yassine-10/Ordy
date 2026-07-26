'use strict';
// Express route scanner. Resolves each endpoint's METHOD + full PATH + auth requirement by
// (1) reading how routers are mounted in the app entry, and (2) reading each router file.
// Regex-based on purpose: no TypeScript compile, no project install — it must run on a
// stranger's repo with nothing but Node. Anything it can't parse is simply not reported,
// which the matcher treats as "not detected → native fallback" rather than a hard failure.

const fs = require('fs');
const path = require('path');
const { find } = require('./detect');

const METHODS = ['get', 'post', 'put', 'patch', 'delete'];
const AUTH_HINTS = /\b(authenticate|authorize\w*|requireAuth|protect|isAuth\w*|ensureAuth\w*|verifyToken|jwt)\b/i;

function read(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch {
    return '';
  }
}

/** Extract the argument text of every `<obj>.<method>(...)` call, paren-balanced. */
function callsFor(text, obj) {
  const out = [];
  const re = new RegExp(`\\b${obj}\\.(${METHODS.join('|')})\\s*\\(`, 'g');
  let m;
  while ((m = re.exec(text))) {
    const method = m[1];
    let i = re.lastIndex;
    let depth = 1;
    const start = i;
    while (i < text.length && depth > 0) {
      const c = text[i];
      if (c === '(') depth++;
      else if (c === ')') depth--;
      i++;
    }
    out.push({ method, args: text.slice(start, i - 1) });
  }
  return out;
}

function firstStringLiteral(s) {
  const m = s.match(/^\s*(['"`])([^'"`]*)\1/);
  return m ? m[2] : null;
}

/** Map imported/required identifiers to their module path. */
function importMap(text) {
  const map = {};
  for (const m of text.matchAll(/import\s+(\w+)\s+from\s+['"]([^'"]+)['"]/g)) map[m[1]] = m[2];
  for (const m of text.matchAll(/(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)/g))
    map[m[1]] = m[2];
  return map;
}

function joinPath(prefix, sub) {
  const a = (prefix || '').replace(/\/+$/, '');
  const b = (sub || '').replace(/^\/?/, '/');
  let joined = (a + b).replace(/\/{2,}/g, '/');
  if (joined.length > 1) joined = joined.replace(/\/$/, ''); // drop trailing slash except root
  return joined === '' ? '/' : joined;
}

function resolveModuleToFile(fromFile, modPath, routeFiles) {
  // Try a real relative resolution first, then fall back to basename matching.
  const base = path.basename(modPath).replace(/\.(t|j)s$/, '');
  const guess = path.resolve(path.dirname(fromFile), modPath);
  const hit = routeFiles.find(
    (f) => f === guess || f.replace(/\.(t|j)s$/, '') === guess || path.basename(f).replace(/\.(t|j)s$/, '') === base
  );
  return hit || null;
}

function scanRoutes(info) {
  const endpoints = [];
  const appEntry = info.files.appEntry;
  if (!appEntry) return endpoints;

  const appText = read(appEntry);
  const imports = importMap(appText);

  // Candidate router files: everything in detected routes/ dirs, plus imported modules.
  const routeFiles = new Set();
  for (const dir of info.files.routeDirs) {
    for (const f of find(dir, /\.(ts|js)$/, 2)) routeFiles.add(f);
  }
  const routeFileList = [...routeFiles];

  // 1) Direct routes declared on the app object itself (e.g. webhooks mounted pre-parser).
  const appObj = (appText.match(/(?:const|let|var)\s+(\w+)\s*=\s*express\(\)/) || [])[1] || 'app';
  for (const call of callsFor(appText, appObj)) {
    const p = firstStringLiteral(call.args);
    if (!p) continue;
    endpoints.push({
      method: call.method.toUpperCase(),
      path: p,
      auth: AUTH_HINTS.test(call.args),
      source: path.basename(appEntry),
    });
  }

  // 2) Mounted routers: `app.use('/api/x', xRouter)` → resolve xRouter's file and prefix it.
  for (const m of appText.matchAll(new RegExp(`${appObj}\\.use\\(\\s*(['"\`])([^'"\`]+)\\1\\s*,\\s*(\\w+)`, 'g'))) {
    const prefix = m[2];
    const ident = m[3];
    const modPath = imports[ident];
    if (!modPath) continue;
    const file = resolveModuleToFile(appEntry, modPath, routeFileList);
    if (!file) continue;
    const routerText = read(file);
    const routerObj =
      (routerText.match(/(?:const|let|var)\s+(\w+)\s*=\s*(?:express\.)?Router\(\)/) || [])[1] || 'router';
    for (const call of callsFor(routerText, routerObj)) {
      const sub = firstStringLiteral(call.args);
      if (sub === null) continue;
      endpoints.push({
        method: call.method.toUpperCase(),
        path: joinPath(prefix, sub),
        auth: AUTH_HINTS.test(call.args),
        source: path.basename(file),
      });
    }
  }

  // De-dupe (method + path).
  const seen = new Set();
  return endpoints.filter((e) => {
    const k = `${e.method} ${e.path}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

module.exports = { scanRoutes };
