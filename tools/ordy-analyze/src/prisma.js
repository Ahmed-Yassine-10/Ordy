'use strict';
// Minimal Prisma schema reader. We only need the shape of the data model — entities, their
// scalar fields, and enums — to (a) show the owner what Ordy understood and (b) help the
// capability matcher (a `Product` model with a `price` is a strong menu signal, an `Order`
// model with `status` is a strong order signal). Full Prisma grammar is out of scope.

const fs = require('fs');

function parsePrismaSchema(file) {
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return { entities: [], enums: [] };
  }
  // Strip comments.
  text = text.replace(/\/\/.*$/gm, '');

  const enums = [];
  for (const m of text.matchAll(/enum\s+(\w+)\s*\{([^}]*)\}/g)) {
    const values = m[2]
      .split(/\s+/)
      .map((v) => v.trim())
      .filter(Boolean);
    enums.push({ name: m[1], values });
  }

  const entities = [];
  for (const m of text.matchAll(/model\s+(\w+)\s*\{([^}]*)\}/g)) {
    const name = m[1];
    const body = m[2];
    const fields = [];
    for (const line of body.split('\n')) {
      const t = line.trim();
      if (!t || t.startsWith('@@')) continue;
      const fm = t.match(/^(\w+)\s+([\w[\]]+)(\?)?/);
      if (!fm) continue;
      fields.push({
        name: fm[1],
        type: fm[2].replace(/[[\]?]/g, ''),
        optional: Boolean(fm[3]) || t.includes('?'),
        list: fm[2].includes('[]'),
      });
    }
    entities.push({ name, fields });
  }
  return { entities, enums };
}

/** Convenience: does the model set have an entity whose name matches, with a given field? */
function hasEntity(model, nameRe, fieldRe) {
  return model.entities.some(
    (e) =>
      nameRe.test(e.name) &&
      (!fieldRe || e.fields.some((f) => fieldRe.test(f.name)))
  );
}

module.exports = { parsePrismaSchema, hasEntity };
