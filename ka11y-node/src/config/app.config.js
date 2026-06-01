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
    // Per-page custom-checks budget (ms). Split 60/40 inside runAll between
    // static and interactive phases so partial results survive a timeout (the
    // previous single-budget Promise.race forfeited every check on a slow page).
    //
    // Default dropped from 90s → 30s on 2026-05-29. Profiling kao.com showed
    // per-page wall time was ≥95s (3s axe.run + ~90s custom-checks), so the
    // 255s overall budget always clipped multi-page crawls at 3 pages. The
    // split-budget cooperative timeout already preserves whichever phase
    // finishes first, so a 30s cap surfaces violations the heavy passes
    // would have found anyway while letting the snapshot-fed crawl actually
    // visit every discovered page. Tune up via the env var if a specific
    // site needs the longer per-page interactive coverage.
    //
    // See ka11y-docs/internals/stage-timing.mdx for how to read which phase
    // hit the cap in the per-(page, stage) summary log.
    customChecksTimeoutMs: parseInt(process.env.CUSTOM_CHECKS_TIMEOUT_MS) || 30_000,
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
