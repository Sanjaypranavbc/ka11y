'use strict';

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
    defaultTags: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'],
    runOnly: {
      type: 'tag',
      values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'],
    },
  },

  browser: {
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  },
  
  cors: {
    origin: /^http:\/\/localhost(:\d+)?$/, // Only allow localhost with any port
  },
};

module.exports = config;
