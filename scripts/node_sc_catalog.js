#!/usr/bin/env node
'use strict';

const path = require('path');

const projectRoot = path.resolve(__dirname, '..', 'ka11y-node');
const axe = require(path.join(projectRoot, 'node_modules/axe-core'));
const { extractSuccessCriteriaId } = require(path.join(projectRoot, 'src/utils/axeResultMapper'));
const config = require(path.join(projectRoot, 'src/config/app.config'));
const customChecks = require(path.join(projectRoot, 'src/custom-checks/index'));

function isScId(v) {
  return typeof v === 'string' && /^\d+\.\d+\.\d+$/.test(v);
}

function main() {
  const out = new Set();

  const rules = axe.getRules(config.axe.runOnly.values);
  for (const rule of rules) {
    const sc = extractSuccessCriteriaId(rule.tags || [], rule.ruleId || rule.id || '');
    if (isScId(sc)) out.add(sc);
  }

  const defs = customChecks._loadCheckDefinitions(path.join(projectRoot, 'src/custom-checks'));
  for (const d of defs) {
    const sc = d && d.check && d.check.SC;
    if (isScId(sc)) out.add(sc);
  }

  const sorted = [...out].sort((a, b) => {
    const pa = a.split('.').map(Number);
    const pb = b.split('.').map(Number);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const da = pa[i] || 0;
      const db = pb[i] || 0;
      if (da !== db) return da - db;
    }
    return 0;
  });

  process.stdout.write(JSON.stringify({ sc: sorted }));
}

main();
