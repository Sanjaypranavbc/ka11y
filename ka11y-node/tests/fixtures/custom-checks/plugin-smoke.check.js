'use strict';

const SC = '2.4.6';
const RULE_ID = 'plugin-smoke-check';
const MODE = 'static';
const DESCRIPTION = 'Fixture plugin rule loaded from the filesystem';
const HELP_URL = 'https://example.com/plugin-smoke';

async function run() {
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: DESCRIPTION,
      impact: null,
      status: 'pass',
      reason: 'Fixture plugin executed.',
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { DESCRIPTION, HELP_URL, MODE, RULE_ID, SC, run };
