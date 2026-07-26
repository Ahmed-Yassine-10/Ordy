'use strict';
// Project detection — figure out what kind of backend we're looking at before we try to
// read anything out of it. Deliberately shallow and tolerant: a wrong guess degrades to
// "unknown" and the analyzer still emits a native-only map rather than crashing.

const fs = require('fs');
const path = require('path');

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function exists(p) {
  try {
    fs.accessSync(p);
    return true;
  } catch {
    return false;
  }
}

/** Walk up to `maxDepth` for a file/dir matching `name` under `root`, skipping noise. */
function find(root, name, maxDepth = 3) {
  const skip = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage']);
  const out = [];
  const walk = (dir, depth) => {
    if (depth > maxDepth) return;
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name.startsWith('.') && e.name !== '.env') continue;
      const full = path.join(dir, e.name);
      const isMatch = e.name === name || (name instanceof RegExp && name.test(e.name));
      if (e.isDirectory()) {
        if (isMatch) out.push(full); // a matching DIRECTORY counts (e.g. routes/)
        if (!skip.has(e.name)) walk(full, depth + 1);
      } else if (isMatch) {
        out.push(full);
      }
    }
  };
  walk(root, 0);
  return out;
}

function detect(root) {
  const info = {
    root,
    language: 'unknown',
    framework: 'unknown',
    orm: 'unknown',
    packageName: null,
    apiBasePath: '/api',
    currency: process.env.ORDY_CURRENCY || 'TND',
    files: { pkg: null, prismaSchema: null, appEntry: null, routeDirs: [] },
  };

  // package.json — language + framework + name. In a monorepo the ROOT manifest is often an
  // empty umbrella; prefer whichever manifest actually declares a server/ORM dependency, so
  // we read backend/package.json rather than the workspace root.
  const pkgs = find(root, 'package.json', 3).filter((f) => !f.includes('node_modules'));
  const SERVER_DEPS = ['express', 'fastify', '@nestjs/core', 'next', '@prisma/client', 'prisma', 'typeorm', 'sequelize', 'mongoose'];
  const scored = pkgs
    .map((f) => {
      const pkg = readJSON(f) || {};
      const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
      return { file: f, hits: SERVER_DEPS.filter((d) => deps[d]).length };
    })
    .sort((a, b) => b.hits - a.hits || a.file.length - b.file.length);
  const pkgFile = (scored[0] && scored[0].hits > 0 ? scored[0].file : null) || pkgs.sort((a, b) => a.length - b.length)[0] || null;
  if (pkgFile) {
    info.files.pkg = pkgFile;
    const pkg = readJSON(pkgFile) || {};
    info.packageName = pkg.name || null;
    const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
    info.language = deps.typescript || exists(path.join(path.dirname(pkgFile), 'tsconfig.json'))
      ? 'typescript'
      : 'javascript';
    if (deps.express) info.framework = 'express';
    else if (deps.fastify) info.framework = 'fastify';
    else if (deps['@nestjs/core']) info.framework = 'nestjs';
    else if (deps.next) info.framework = 'next';
    if (deps['@prisma/client'] || deps.prisma) info.orm = 'prisma';
    else if (deps.typeorm) info.orm = 'typeorm';
    else if (deps.sequelize) info.orm = 'sequelize';
    else if (deps.mongoose) info.orm = 'mongoose';
  }

  // Prisma schema — the richest data-model source when present.
  const schemas = find(root, 'schema.prisma', 4);
  if (schemas.length) {
    info.files.prismaSchema = schemas[0];
    if (info.orm === 'unknown') info.orm = 'prisma';
  }

  // App entry (route mounting) — app.ts / server.ts / index.ts near a routes/ dir.
  const entries = find(root, /^(app|server|index|main)\.(ts|js)$/, 4).filter(
    (f) => !f.includes('node_modules') && !f.includes(`${path.sep}dist${path.sep}`)
  );
  // Prefer one whose sibling tree contains a routes/ directory.
  const routeDirs = find(root, /^routes?$/, 4).filter(
    (f) => fs.statSync(f).isDirectory() && !f.includes('node_modules')
  );
  info.files.routeDirs = routeDirs;
  info.files.appEntry =
    entries.sort((a, b) => a.length - b.length).find((e) => e.match(/app\.(ts|js)$/)) ||
    entries[0] ||
    null;

  return info;
}

module.exports = { detect, find, readJSON, exists };
