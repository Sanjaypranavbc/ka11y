'use strict';

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const DEFAULT_SHARED_CONFIG_PATH = path.resolve(__dirname, '../../../config/universal.yml');
const SHARED_CONFIG_PATH = process.env.A11Y_SHARED_CONFIG_PATH || DEFAULT_SHARED_CONFIG_PATH;

function _loadYaml(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return yaml.load(raw) || {};
  } catch (err) {
    if (err.code !== 'ENOENT') {
      process.stderr.write(`[sharedConfigLoader] YAML parse error in ${filePath}: ${err.message}\n`);
    }
    return {};
  }
}

function loadSharedConfig() {
  return _loadYaml(SHARED_CONFIG_PATH);
}

function getSharedConfigValue(pathParts, defaultValue = null, config = loadSharedConfig()) {
  let current = config;
  for (const part of pathParts) {
    if (!current || typeof current !== 'object' || !(part in current)) {
      return defaultValue;
    }
    current = current[part];
  }
  return current == null ? defaultValue : current;
}

module.exports = {
  SHARED_CONFIG_PATH,
  getSharedConfigValue,
  loadSharedConfig,
};
