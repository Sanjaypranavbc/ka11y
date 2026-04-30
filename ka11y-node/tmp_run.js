#!/usr/bin/env node
'use strict';
const path = require('path');
const AccessibilityService = require('./src/services/accessibility.service');
const puppeteer = require('puppeteer');
const axePath = (() => {
  try { return require.resolve('axe-core/axe.min.js'); } catch(e) { return path.resolve(__dirname,'node_modules/axe-core/axe.min.js'); }
})();
const logger = console;
const config = {
  browser: { headless: true, args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu']},
  axe: { timeoutMs: 30000, runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag22a','best-practice'] } },
  payload: { limit: '10mb' }
};
const svc = new AccessibilityService(puppeteer, axePath, logger, config);
(async () => {
  try {
    const res = await svc.analyseUrl('https://www.bbc.com/sport', null, 'en');
    console.log(JSON.stringify(res, null, 2));
    process.exit(0);
  } catch (e) {
    console.error('ERROR', e && e.stack || e);
    process.exit(2);
  }
})();
