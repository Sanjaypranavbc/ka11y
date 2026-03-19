'use strict';

const fs   = require('fs');
const path = require('path');

const COLORS = {
  info:  '\x1b[36m[INFO] \x1b[0m',
  warn:  '\x1b[33m[WARN] \x1b[0m',
  error: '\x1b[31m[ERROR]\x1b[0m',
  debug: '\x1b[35m[DEBUG]\x1b[0m',
};

const LOG_DIR = path.resolve(__dirname, '../../logs');

function getLogPath(level) {
  const now   = new Date();
  const year  = now.getFullYear().toString();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day   = String(now.getDate()).padStart(2, '0');
  const dir   = path.join(LOG_DIR, year, month, day);
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${level}.log`);
}

function timestamp() {
  return new Date().toISOString();
}

function log(level, message, meta = null) {
  const ts     = timestamp();
  const color  = COLORS[level] || COLORS.info;
  const consoleLine = `${color} [${ts}] ${message}`;
  const fileLine    = `[${level.toUpperCase()}] [${ts}] ${message}${meta ? ' ' + JSON.stringify(meta) : ''}\n`;

  // Console output (colored)
  if (meta) {
    console.log(consoleLine, meta);
  } else {
    console.log(consoleLine);
  }

  // File output (non-blocking)
  fs.promises.appendFile(getLogPath(level), fileLine).catch(err => {
    console.error(`[logger] Failed to write ${level} log:`, err.message);
  });
}

const logger = {
  info:  (msg, meta) => log('info',  msg, meta),
  warn:  (msg, meta) => log('warn',  msg, meta),
  error: (msg, meta) => log('error', msg, meta),
  debug: (msg, meta) => log('debug', msg, meta),
};

module.exports = logger;
