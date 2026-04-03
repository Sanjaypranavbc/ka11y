#!/usr/bin/env node
'use strict';

const path = require('path');

const projectRoot = path.resolve(__dirname, '..', 'ka11y-node');
const config = require(path.join(projectRoot, 'src/config/app.config'));
const AccessibilityService = require(path.join(projectRoot, 'src/services/accessibility.service'));
const puppeteer = require(path.join(projectRoot, 'node_modules/puppeteer'));

const logger = {
  info: () => {},
  warn: () => {},
  error: () => {},
  debug: () => {},
};

async function main() {
  const url = process.argv[2];
  const level = process.argv[3] || 'AAA';
  const lang = process.argv[4] || 'en';

  if (!url) {
    process.stdout.write(JSON.stringify({ error: 'Missing URL argument' }));
    process.exit(1);
  }

  const service = new AccessibilityService(
    puppeteer,
    path.join(projectRoot, 'node_modules/axe-core/axe.min.js'),
    logger,
    config,
  );

  const started = Date.now();
  try {
    const findings = await service.analyseUrlFlat(url, level, lang);
    const runtimeSeconds = (Date.now() - started) / 1000;
    process.stdout.write(JSON.stringify({ findings, runtimeSeconds }));
  } catch (err) {
    const runtimeSeconds = (Date.now() - started) / 1000;
    process.stdout.write(JSON.stringify({
      error: err && err.message ? err.message : String(err),
      runtimeSeconds,
    }));
    process.exit(2);
  }
}

main();
