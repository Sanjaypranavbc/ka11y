'use strict';

const { getSharedConfigValue } = require('../utils/sharedConfigLoader');

function _envBool(name, fallback) {
  const raw = process.env[name];
  if (raw == null || raw === '') return fallback;
  const val = String(raw).trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(val)) return true;
  if (['0', 'false', 'no', 'off'].includes(val)) return false;
  return fallback;
}

/**
 * Centralised application configuration.
 * All process.env reads happen here — nowhere else in the codebase.
 */
const config = {
  port: parseInt(process.env.PORT) || 3000,

  payload: {
    limit: process.env.BODY_LIMIT || '10mb',
  },

  axe: {
    timeoutMs: parseInt(process.env.AXE_TIMEOUT_MS) || 30_000,
    // Per-page custom-checks budget (ms). Modest so one page can't dominate a
    // multi-page crawl. Was 180_000 hard-coded; lowered + made tunable.
    customChecksTimeoutMs: parseInt(process.env.CUSTOM_CHECKS_TIMEOUT_MS) || 60_000,
    // Overall multi-page (flat) crawl budget (ms). MUST stay below the Python
    // combined runner's _call_node_flat HTTP timeout (300s) so a deep crawl
    // returns partial findings instead of the caller timing out and discarding
    // everything.
    flatCrawlBudgetMs: parseInt(process.env.FLAT_CRAWL_BUDGET_MS) || 255_000,
    // Per-page hard cap (ms) for the flat crawl; clamped to the remaining
    // overall budget so the loop stays responsive when a single page hangs.
    flatPerPageMs: parseInt(process.env.FLAT_PER_PAGE_MS) || 120_000,
    defaultTags: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa'],
    runOnly: {
      type: 'tag',
      values: ['wcag2a', 'wcag2aa', 'wcag2aaa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa', 'best-practice'],
    },
  },

  browser: {
    headless: 'shell',
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
    ignoreHTTPSErrors: _envBool(
      'PUPPETEER_IGNORE_HTTPS_ERRORS',
      Boolean(getSharedConfigValue(['browser', 'ignore_https_errors'], true)),
    ),
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-zygote',
      '--no-first-run',
      '--disable-crash-reporter',
      '--disable-breakpad',
    ],
  },
  
};

module.exports = config;
