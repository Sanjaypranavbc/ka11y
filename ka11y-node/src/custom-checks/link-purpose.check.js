'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '2.4.9';
const RULE_ID = 'custom-link-purpose';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-link-only';

// Generic link text that conveys no purpose when read in isolation (AAA criterion).
// Includes Japanese equivalents of "click here", "details", "more", etc.
const GENERIC_LINK_RE = /^(click\s+here|here|read\s+more|more|learn\s+more|more\s+info(rmation)?|details|continue|go|link|this|see\s+more|view\s+more|find\s+out\s+more|click|tap|press\s+here|start|begin|open|show|hide|toggle|こちら|こちらへ|詳細|詳しくはこちら|詳細はこちら|もっと見る|続きを読む|もっと読む|続きはこちら|詳しく見る|もっと詳しく|開く|見る|確認する|ここをクリック|クリック|タップ|詳細を見る|さらに|リンク)\.?$/i;

const MAX_LINKS = 100;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
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
        const labelledBy = (link.getAttribute('aria-labelledby') || '').trim();
        if (labelledBy) {
          const ids = labelledBy.split(/\s+/).filter(Boolean);
          const parts = ids
            .map(id => {
              const node = document.getElementById(id);
              return node ? (node.textContent || '').trim() : '';
            })
            .filter(Boolean);
          if (parts.length > 0) accessibleName = parts.join(' ');
        }
      }

      if (!accessibleName) {
        const img = link.querySelector('img');
        if (img && !(link.textContent || '').trim()) {
          accessibleName = (img.getAttribute('alt') || '').trim();
        } else {
          // Collect only visible text — textContent includes display:none descendants
          // which can make a generic link appear descriptive (false negative).
          const visibleText = [];
          const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
              const parent = node.parentElement;
              if (!parent) return NodeFilter.FILTER_REJECT;
              const cs = window.getComputedStyle(parent);
              if (cs.display === 'none' || cs.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
              return NodeFilter.FILTER_ACCEPT;
            },
          });
          let n;
          while ((n = walker.nextNode())) {
            const t = (n.nodeValue || '').trim();
            if (t) visibleText.push(t);
          }
          accessibleName = visibleText.join(' ').replace(/\s+/g, ' ').trim();
        }
      }

      if (!accessibleName) {
        accessibleName = (link.getAttribute('title') || '').trim();
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
          ? _t(sharedContext, '{count} link(s) checked — none use generic text like "click here" or "read more" that would be ambiguous in isolation.', 'リンク {count} 件を確認しましたが、単独で読むと意味が曖昧になる汎用的なリンク文言は検出されませんでした。', { count: data.checkedCount })
          : _t(sharedContext, 'No links found to check.', '確認対象のリンクは見つかりませんでした。'),
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
      reason: _t(sharedContext, '{count} link(s) use generic text that does not describe the destination when read alone: {sample}. Replace with descriptive text or provide an aria-label with the full link purpose.', '単独で読むとリンク先の目的が分からない汎用的なリンク文言が {count} 件検出されました: {sample}。説明的なリンクテキストに置き換えるか、完全なリンク目的を示す aria-label を付与してください。', { count: data.violations.length, sample }),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
