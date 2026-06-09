'use strict';

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.3.3';
const RULE_ID = 'custom-sensory-characteristics';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/sensory-characteristics';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Instructions must not rely solely on shape, color, size, visual location, or sound';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _pass(ctx, reason) {
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass', reason, helpUrl: HELP_URL }],
  };
}

// Detects phrases that identify a UI element only by sensory characteristic
// e.g. "click the round button", "the button on the right", "use the green icon"
const SENSORY_PATTERNS = [
  // Shape-only identification
  /\bthe\s+(?:round|square|circular|triangular|arrow|star|oval|rectangular|diamond)\s+(?:button|icon|link|field|input|box|image|control)\b/i,
  // Position-only identification
  /\b(?:click|tap|select|press|use)\s+the\s+(?:button|link|icon|image|control)\s+(?:on\s+the\s+)?(?:right|left|above|below|top|bottom|upper|lower|opposite)\b/i,
  /\bthe\s+(?:right|left|top|bottom|upper|lower)\s+(?:button|link|icon|input|image|control|element)\b/i,
  // Color-only identification
  /\b(?:click|tap|select|press|use)\s+the\s+(?:red|blue|green|yellow|orange|purple|gray|grey|black|white|pink|cyan|magenta)\s+(?:button|link|icon|image|control)\b/i,
  /\bthe\s+(?:red|blue|green|yellow|orange|purple|gray|grey|black|white|pink|cyan|magenta)\s+(?:button|link|icon|image|control|area|section|region)\b/i,
  // Sound-only identification
  /\bwhen\s+you\s+hear\s+the\s+(?:beep|chime|tone|sound|bell|alert)\b/i,
];

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate((patterns) => {
    const regexes = patterns.map(p => new RegExp(p.source, p.flags));
    const issues = [];

    // Check instructional text in likely containers
    const containers = document.querySelectorAll('p,li,label,legend,caption,figcaption,[role="note"],[role="doc-tip"],td,th');
    for (const el of containers) {
      const text = (el.textContent || '').trim();
      if (!text) continue;
      for (const re of regexes) {
        const match = text.match(re);
        if (match) {
          issues.push({
            target: el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : ''),
            snippet: text.slice(0, 150),
            match: match[0],
          });
          break; // one finding per element
        }
      }
    }
    return { issues };
  }, SENSORY_PATTERNS.map(r => ({ source: r.source, flags: r.flags })));

  if (!data.issues.length) {
    return _pass(ctx, _t(ctx,
      'No sensory-only instruction patterns detected.',
      '感覚的特性のみに依存した指示のパターンは検出されませんでした。'));
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'moderate',
      status: 'incomplete',
      reason: _t(ctx,
        '{n} instruction(s) may rely solely on sensory characteristics (shape, color, or position). Manual review required.',
        '{n} 件の指示が感覚的特性（形状・色・位置）のみに依存している可能性があります。手動確認が必要です。',
        { n: data.issues.length }),
      elements: data.issues,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
