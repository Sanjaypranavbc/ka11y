'use strict';

const SC = '1.3.4';
const RULE_ID = 'custom-orientation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/orientation';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Content must not restrict its view and operation to a single display orientation';

async function run(page) {
  const findings = await page.evaluate(() => {
    const issues = [];

    // ── 1. Detect screen.orientation.lock / lockOrientation calls in inline scripts ──
    const scripts = Array.from(document.querySelectorAll('script:not([src])'));
    for (const script of scripts) {
      const src = script.textContent || '';
      if (/screen\s*\.\s*orientation\s*\.\s*lock\s*\(/.test(src) ||
          /screen\s*\.\s*lockOrientation\s*\(/.test(src) ||
          /screen\s*\.\s*mozLockOrientation\s*\(/.test(src) ||
          /screen\s*\.\s*msLockOrientation\s*\(/.test(src)) {
        issues.push({
          type: 'script-lock',
          reason: 'Inline script calls screen.orientation.lock() or a vendor-prefixed equivalent, which may lock the page to a specific orientation.',
        });
        break; // one report is enough
      }
    }

    // ── 2. Detect CSS transform: rotate that forces layout rotation ──
    // Major layout containers (body, main, #app, #root, .wrapper, etc.) with a
    // 90° / 270° rotation are a strong signal of orientation locking.
    const LAYOUT_SELECTORS = ['body', 'main', '#app', '#root', '#wrapper', '.wrapper', '.container', '.page'];
    const FORCED_ROTATIONS = /rotate\(\s*(-?(?:90|270)deg|-?(?:0\.5|1\.5)turn)\s*\)/;
    for (const sel of LAYOUT_SELECTORS) {
      let el;
      try { el = document.querySelector(sel); } catch (_) { continue; }
      if (!el) continue;
      const transform = window.getComputedStyle(el).transform || '';
      // getComputedStyle returns matrix() notation; also check inline style
      const inlineTransform = el.style.transform || '';
      if (FORCED_ROTATIONS.test(inlineTransform)) {
        issues.push({
          type: 'css-rotate',
          reason: `Element <${el.tagName.toLowerCase()}${el.id ? ' id="' + el.id + '"' : ''}> has transform:rotate(90/270deg) applied inline, which forces a specific visual orientation.`,
        });
        break;
      }
    }

    // ── 3. Detect CSS @media orientation rules in <style> tags that hide main content ──
    // We scan embedded stylesheets for orientation media queries combined with
    // display:none / visibility:hidden on major structural elements.
    const ORIENTATION_HIDE = /@media[^{]*orientation\s*:\s*(portrait|landscape)[^{]*\{[^}]*(?:display\s*:\s*none|visibility\s*:\s*hidden)/i;
    const styleEls = Array.from(document.querySelectorAll('style'));
    for (const styleEl of styleEls) {
      const css = styleEl.textContent || '';
      const match = css.match(/@media[^{]*orientation\s*:\s*(portrait|landscape)/i);
      if (match && ORIENTATION_HIDE.test(css)) {
        issues.push({
          type: 'css-media-hide',
          reason: `A <style> block contains @media orientation:${match[1]} with display:none or visibility:hidden, which may prevent access in one orientation.`,
        });
        break;
      }
    }

    // ── 4. Detect meta viewport content="... orientation=lock" (non-standard but used) ──
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport) {
      const content = (viewport.getAttribute('content') || '').toLowerCase();
      if (content.includes('orientation=')) {
        issues.push({
          type: 'meta-viewport-orientation',
          reason: `<meta name="viewport"> includes "orientation=" which attempts to restrict the page orientation via the viewport meta tag.`,
        });
      }
    }

    return issues;
  });

  if (findings.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact: null,
        status: 'pass',
        reason: 'No orientation-locking patterns detected (screen.orientation.lock, forced CSS rotation, or orientation-hiding media queries).',
        helpUrl: HELP_URL,
      }],
    };
  }

  const summary = findings.map(f => f.reason).join(' | ');

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: FALLBACK_DESCRIPTION,
      impact: 'serious',
      status: 'incomplete',
      reason: `${findings.length} orientation-restriction issue(s) detected. Verify that content is accessible in both portrait and landscape. Details: ${summary}`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
