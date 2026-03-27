'use strict';

const SC = '2.4.9';
const RULE_ID = 'custom-link-purpose';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-link-only';

// Generic link text that conveys no purpose when read in isolation (AAA criterion).
// Includes Japanese equivalents of "click here", "details", "more", etc.
const GENERIC_LINK_RE = /^(click\s+here|here|read\s+more|more|learn\s+more|more\s+info(rmation)?|details|continue|go|link|this|see\s+more|view\s+more|find\s+out\s+more|click|tap|press\s+here|start|begin|open|show|hide|toggle|こちら|こちらへ|詳細|詳しくはこちら|詳細はこちら|もっと見る|続きを読む|続きはこちら|詳しく見る|もっと詳しく|開く|見る|確認する|ここをクリック|クリック|タップ|詳細を見る)\.?$/i;

const MAX_LINKS = 100;

async function run(page) {
  const data = await page.evaluate((maxLinks, genericRe) => {
    const re = new RegExp(genericRe);
    const seen = new Set();
    const violations = [];
    let checkedCount = 0;

    for (const link of document.querySelectorAll('a[href]')) {
      if (seen.has(link)) continue;
      seen.add(link);
      if (seen.size > maxLinks) break;

      // Build accessible name: aria-label > aria-labelledby > img[alt] > text content
      let accessibleName = (link.getAttribute('aria-label') || '').trim();

      if (!accessibleName) {
        const labelledById = link.getAttribute('aria-labelledby');
        if (labelledById) {
          const labelEl = document.getElementById(labelledById);
          if (labelEl) accessibleName = (labelEl.textContent || '').trim();
        }
      }

      if (!accessibleName) {
        const img = link.querySelector('img');
        if (img && !(link.textContent || '').trim()) {
          accessibleName = (img.getAttribute('alt') || '').trim();
        } else {
          accessibleName = (link.textContent || '').trim().replace(/\s+/g, ' ');
        }
      }

      // Skip icon-only links with no text (axe `link-name` rule covers these)
      if (!accessibleName) continue;

      checkedCount++;

      if (re.test(accessibleName)) {
        violations.push({
          text: accessibleName.slice(0, 60),
          html: link.outerHTML.slice(0, 150),
          id:   link.id || null,
        });
      }
    }

    return { violations, checkedCount };
  }, MAX_LINKS, GENERIC_LINK_RE.source);

  if (data.violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Link purpose must be determinable from link text alone',
        impact: null,
        status: 'pass',
        reason: data.checkedCount > 0
          ? `${data.checkedCount} link(s) checked — none use generic text like "click here" or "read more" that would be ambiguous in isolation.`
          : 'No links found to check.',
        helpUrl: HELP_URL,
      }],
    };
  }

  const sample = data.violations.slice(0, 3).map(v => `"${v.text}"`).join(', ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Link purpose must be determinable from link text alone',
      impact: 'moderate',
      status: 'fail',
      reason: `${data.violations.length} link(s) use generic text that does not describe the destination when read alone: ${sample}. Replace with descriptive text or provide an aria-label with the full link purpose.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };