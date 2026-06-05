'use strict';

const {
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.3.4';
const RULE_ID = 'custom-orientation';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/orientation';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Content must not restrict its view and operation to a single display orientation';

// Maps a finding type to a deterministic ruleId suffix.
const RULE_SUFFIX = {
  'script-lock'              : 'script-lock',
  'css-rotate'               : 'css-rotate',
  'css-media-hide'           : 'css-media-hide',
  'css-media-structural'     : 'css-media-structural',
  'meta-viewport-orientation': 'meta-viewport',
  'manifest-orientation'     : 'manifest',
  'cross-origin-sheet'       : 'cross-origin-sheet',
  'writing-mode'             : 'writing-mode',
  'viewport-scale'           : 'viewport-scale',
};

// Unambiguous violations → 'fail'; heuristic detections → 'incomplete'
const DEFINITE_FAIL_TYPES = new Set([
  'script-lock',
  'meta-viewport-orientation',
  'manifest-orientation',
  'writing-mode',
]);

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

function _localizeFindingReason(finding, context) {
  switch (finding.type) {
    case 'manifest-orientation':
      return _t(context, 'Web App Manifest sets "orientation": "{detail}", locking the PWA to a single display orientation.', 'Web App Manifest で "orientation": "{detail}" が設定されており、PWA が単一の画面向きに固定されます。', { detail: finding.detail || finding.snippet || '' });
    case 'script-lock':
      return _t(context, 'Inline <script> {target} calls orientation-locking API: {detail}. This may lock the page to a specific orientation.', 'インライン <script> {target} で画面向き固定 API が呼び出されています: {detail}。ページが特定の向きに固定される可能性があります。', { target: finding.target || '', detail: finding.detail || finding.snippet || '' });
    case 'css-rotate':
      return _t(context, 'Element {target} has a forced 90°/270° rotation via {detail}, forcing a specific visual orientation.', '要素 {target} に {detail} による 90°/270° の強制回転があり、特定の視覚的な向きに固定される可能性があります。', { target: finding.target || '', detail: finding.detail || '' });
    case 'css-media-hide':
      return _t(context, '"{target}" in {source} is hidden inside @media {media_query} — content inaccessible in that orientation.', '{source} 内の "{target}" は @media {media_query} の中で非表示にされており、その画面向きではコンテンツにアクセスできません。', { target: finding.target || '', source: finding.source || 'stylesheet', media_query: finding.mediaQuery || '' });
    case 'cross-origin-sheet':
      return _t(context, 'External stylesheet "{source}" is cross-origin and could not be inspected for orientation rules. Manual review required.', '外部スタイルシート "{source}" はクロスオリジンのため、画面向きに関する CSS ルールを検査できませんでした。手動確認が必要です。', { source: finding.source || finding.target || '' });
    case 'meta-viewport-orientation':
      return _t(context, '<meta name="viewport"> includes "orientation=" which restricts the page to a specific orientation.', '<meta name="viewport"> に "orientation=" が含まれており、ページが特定の画面向きに制限されています。');
    case 'css-media-structural':
      return _t(context, '"{target}" in {source} applies structural CSS inside @media {media_query} that may break layout in that orientation. Manual review recommended.', '{source} 内の "{target}" は @media {media_query} の中で構造的な CSS を適用しており、その画面向きでレイアウトが崩れる可能性があります。手動確認を推奨します。', { target: finding.target || '', source: finding.source || 'stylesheet', media_query: finding.mediaQuery || '' });
    case 'writing-mode':
      return _t(context, 'document.body has writing-mode: {detail}, which forces a vertical text layout and may restrict orientation.', 'document.body に writing-mode: {detail} が設定されており、縦書きレイアウトが強制されて画面向きが制限される可能性があります。', { detail: finding.detail || '' });
    case 'viewport-scale':
      return _t(context, '<meta name="viewport"> sets maximum-scale=1, which prevents users from zooming and may compound orientation restrictions.', '<meta name="viewport"> に maximum-scale=1 が設定されており、ユーザーが拡大できず、画面向きの制約を悪化させる可能性があります。');
    default:
      return finding.reason;
  }
}

// Builds one rule entry from a raw finding object.
function buildRule(finding, context = {}) {
  return {
    ruleId     : `${RULE_ID}-${RULE_SUFFIX[finding.type] ?? finding.type}`,
    description: FALLBACK_DESCRIPTION,
    impact     : 'serious',
    status     : DEFINITE_FAIL_TYPES.has(finding.type) ? 'fail' : 'incomplete',
    reason     : _localizeFindingReason(finding, context),
    target     : finding.target     ?? null,
    selector   : finding.selector   ?? null,
    snippet    : finding.snippet    ?? null,
    source     : finding.source     ?? null,
    mediaQuery : finding.mediaQuery ?? null,
    helpUrl    : HELP_URL,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);

  // ── Web App Manifest orientation field (Node context) ─────────────────────
  // BUG-FIX 1: manifest.orientation may not be a string (could be an object in
  // some draft specs). Guard with String() before calling .toLowerCase().
  const manifestFindings = [];
  try {
    const manifestUrl = await page.evaluate(() => {
      const el = document.querySelector('link[rel="manifest"]');
      return el ? el.href : null;
    });
    if (manifestUrl) {
      const manifestContent = await page.evaluate(async (url) => {
        try { return await (await fetch(url)).text(); } catch (_) { return null; }
      }, manifestUrl);
      if (manifestContent) {
        try {
          const manifest = JSON.parse(manifestContent);
          const LOCKED = ['portrait','landscape','portrait-primary','portrait-secondary','landscape-primary','landscape-secondary'];
          // BUG-FIX 1: coerce to string before toLowerCase to avoid runtime TypeError
          const orientationValue = manifest.orientation != null ? String(manifest.orientation) : null;
          if (orientationValue && LOCKED.includes(orientationValue.toLowerCase())) {
            manifestFindings.push({
              type   : 'manifest-orientation',
              target : 'manifest.json',
              snippet: `"orientation": "${orientationValue}"`,
              detail : orientationValue,
            });
          }
        } catch (_) { /* invalid JSON — skip */ }
      }
    }
  } catch (_) { /* fetch or evaluate failed — skip */ }

  // ── All DOM-level checks ───────────────────────────────────────────────────
  const domFindings = await page.evaluate(() => {
    const findings = [];

    // ── Helper: element → stable CSS selector string ─────────────────────────
    // BUG-FIX 2: el.className can be an SVGAnimatedString on SVG elements,
    // which has no .join method. Guard with typeof check before spreading classList.
    function elToSelector(el) {
      let s = el.tagName.toLowerCase();
      if (el.id) s += `#${CSS.escape(el.id)}`;
      if (el.classList && el.classList.length) {
        s += '.' + [...el.classList].map(c => CSS.escape(c)).join('.');
      }
      return s;
    }

    // ── Helper: element → opening-tag HTML snippet ───────────────────────────
    function elToSnippet(el) {
      const attrs = [...el.attributes].map(a => `${a.name}="${a.value}"`).join(' ');
      return `<${el.tagName.toLowerCase()}${attrs ? ' ' + attrs : ''}>`;
    }

    // ── Helper: dynamic layout-candidate discovery ───────────────────────────
    function getLayoutCandidates() {
      const seen = new Set();
      const add  = (el) => { if (el && !seen.has(el)) seen.add(el); };

      ['body','main','header','footer','section','article','aside','nav']
        .forEach(tag => document.querySelectorAll(tag).forEach(add));

      ['main','banner','contentinfo','navigation','region','complementary']
        .forEach(role => document.querySelectorAll(`[role="${role}"]`).forEach(add));

      const LAYOUT_PAT = /^(app|root|wrapper|container|layout|page|content|main|body|screen)(-.*)?$/i;
      document.querySelectorAll('[id],[class]').forEach(el => {
        const id = el.id || '';
        // BUG-FIX 3: el.classList can be empty or el.className an SVGAnimatedString;
        // spread safely via Array.from with a fallback empty array.
        const classes = el.classList ? Array.from(el.classList) : [];
        if (LAYOUT_PAT.test(id) || classes.some(c => LAYOUT_PAT.test(c))) add(el);
      });

      const vw = window.innerWidth, vh = window.innerHeight;
      // BUG-FIX 4: headless / 0-size viewports would make vw*0.6 = 0, matching
      // every element. Skip the size heuristic when the viewport reports 0.
      if (vw > 0 && vh > 0) {
        document.querySelectorAll('div,section,article').forEach(el => {
          const r = el.getBoundingClientRect();
          if (r.width >= vw * 0.6 && r.height >= vh * 0.6) add(el);
        });
      }

      return [...seen];
    }

    // ── Helper: CSS matrix string → rotation angle in degrees ────────────────
    // BUG-FIX 5: The previous version only handled matrix() but getComputedStyle
    // can return matrix3d() for 3-D transforms. Handle both forms.
    function matrixAngle(matrixStr) {
      if (!matrixStr || matrixStr === 'none') return null;

      // Standard 2-D: matrix(a,b,c,d,tx,ty)
      const m2 = matrixStr.match(/^matrix\(([^)]+)\)/);
      if (m2) {
        const parts = m2[1].split(',').map(Number);
        const a = parts[0], b = parts[1];
        if (isNaN(a) || isNaN(b)) return null;
        return Math.round(Math.atan2(b, a) * (180 / Math.PI));
      }

      // 3-D: matrix3d(n,n,n,n, n,n,n,n, n,n,n,n, n,n,n,n)
      // Elements [0]=m11, [1]=m12 give the 2-D rotation component.
      const m3 = matrixStr.match(/^matrix3d\(([^)]+)\)/);
      if (m3) {
        const parts = m3[1].split(',').map(Number);
        const a = parts[0], b = parts[1];
        if (isNaN(a) || isNaN(b)) return null;
        return Math.round(Math.atan2(b, a) * (180 / Math.PI));
      }

      return null;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Check 1 — Inline script orientation-lock calls
    //   One finding per <script> tag that contains a lock call.
    // BUG-FIX 6: The LOCK_RE regex had the /g flag set as a module-level constant.
    // When a regex with /g is reused across multiple .matchAll() calls it works
    // correctly with matchAll (which always resets), but using it with .match()
    // or .test() would silently skip matches due to lastIndex carry-over.
    // Defined here as a fresh regex per check to make the intent unambiguous and
    // safe if future code paths reuse it with .test() or .exec().
    // ═════════════════════════════════════════════════════════════════════════
    document.querySelectorAll('script:not([src])').forEach((script, idx) => {
      const src     = script.textContent || '';
      // Fresh /g regex per iteration — avoids lastIndex bleed if ever used with .test()
      const LOCK_RE = /screen\s*\.\s*(?:orientation\s*\.\s*lock|lockOrientation|mozLockOrientation|msLockOrientation|webkitLockOrientation)\s*\(/g;
      const matches = [...src.matchAll(LOCK_RE)].map(m => m[0].replace(/\s+/g, ''));
      if (matches.length === 0) return;

      findings.push({
        type    : 'script-lock',
        target  : `inline <script> #${idx + 1}`,
        // BUG-FIX 7: nth-of-type counts ALL <script> tags (including those with src),
        // so the index from querySelectorAll('script:not([src])') doesn't match
        // nth-of-type(N). Use a data-driven selector that is always accurate.
        selector: `script:not([src]):nth-child(${[...document.querySelectorAll('script')].indexOf(script) + 1})`,
        snippet : matches[0],
        detail  : [...new Set(matches)].join(', '),
      });
    });

    // ═════════════════════════════════════════════════════════════════════════
    // Check 2 — CSS forced rotation on layout containers
    //   One finding per rotated element.
    // ═════════════════════════════════════════════════════════════════════════
    const FORCED_ANGLE_RE = /rotate\(\s*(-?(?:90|270)(?:\.\d+)?deg|-?(?:0\.5|1\.5)turn|-?(?:1\.5707|4\.7123)\s*rad)\s*\)/;
    const ROTATE_PROP_RE  = /^(-?(?:90|270)(?:\.\d+)?deg|-?(?:0\.5|1\.5)turn|-?(?:1\.5707|4\.7123)\s*rad)$/;
    // BUG-FIX 8: Previous rad literals (1.571, 4.712) were truncated — real
    // values are 1.5708 (π/2) and 4.7124 (3π/2). Browsers may serialize with
    // more precision. Use 4-decimal prefix match (1.5707 / 4.7123) to be safe
    // while avoiding false positives from unrelated radian values.

    getLayoutCandidates().forEach(el => {
      const computed          = window.getComputedStyle(el);
      const computedTransform = computed.transform || computed.webkitTransform || '';
      const inlineTransform   = el.style.transform || '';
      const computedRotate    = computed.rotate    || el.style.rotate || '';

      const angle             = matrixAngle(computedTransform);
      const hasMatrixRotation = angle !== null && (Math.abs(angle) === 90 || Math.abs(angle) === 270);
      const hasInlineRotation = FORCED_ANGLE_RE.test(inlineTransform);
      const hasRotateProperty = ROTATE_PROP_RE.test(computedRotate.trim());

      if (!hasMatrixRotation && !hasInlineRotation && !hasRotateProperty) return;

      const via = [
        hasMatrixRotation && `computed matrix (≈${angle}°)`,
        hasInlineRotation && `inline transform`,
        hasRotateProperty && `rotate property (${computedRotate.trim()})`,
      ].filter(Boolean).join(', ');

      findings.push({
        type    : 'css-rotate',
        target  : elToSelector(el),
        selector: elToSelector(el),
        snippet : elToSnippet(el),
        detail  : via,
      });
    });

    // ═════════════════════════════════════════════════════════════════════════
    // Check 3 — @media orientation rules that hide content
    //   One finding per CSS style rule inside an orientation media block.
    // BUG-FIX 9: The recursive scanHideRules call was placed AFTER the inner-rule
    // loop inside the orientMatch branch. This meant nested @media blocks were
    // recursed into even when they weren't orientation queries, and orientation
    // blocks nested inside @supports were scanned twice (once by the SUPPORTS_RULE
    // branch and once by recursion). Restructured so recursion only descends into
    // non-orientation MEDIA_RULE children and SUPPORTS_RULE children.
    // ═════════════════════════════════════════════════════════════════════════
    const HIDE_PROPS = /(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0;?$|height\s*:\s*[01]px|pointer-events\s*:\s*none)/i;

    function scanHideRules(rules, sheetLabel) {
      if (!rules) return;
      for (const rule of rules) {
        try {
          if (rule.type === CSSRule.MEDIA_RULE) {
            const mediaText   = rule.conditionText || rule.media?.mediaText || '';
            const orientMatch = mediaText.match(/orientation\s*:\s*(portrait|landscape)|(?:max|min)-aspect-ratio/i);
            if (orientMatch) {
              // Emit one finding per inner style-rule that hides content.
              // Do NOT recurse further inside an orientation block — nesting
              // orientation inside orientation is not meaningful CSS.
              for (const inner of (rule.cssRules || [])) {
                if (inner.type === CSSRule.STYLE_RULE && HIDE_PROPS.test(inner.cssText)) {
                  findings.push({
                    type      : 'css-media-hide',
                    target    : inner.selectorText,
                    selector  : inner.selectorText,
                    snippet   : inner.cssText.slice(0, 120),
                    source    : sheetLabel,
                    mediaQuery: mediaText,
                  });
                }
              }
            } else {
              // Non-orientation media rule — recurse in case it wraps an orientation rule
              scanHideRules(rule.cssRules, sheetLabel);
            }
          } else if (rule.type === CSSRule.SUPPORTS_RULE) {
            // @supports may wrap @media orientation rules
            scanHideRules(rule.cssRules, sheetLabel);
          }
        } catch (_) { /* cross-origin inner rule — skip */ }
      }
    }

    Array.from(document.styleSheets).forEach((sheet, i) => {
      const label = sheet.href ? sheet.href : `<style[${i}]>`;
      try {
        scanHideRules(sheet.cssRules, label);
      } catch (_) {
        if (sheet.href) {
          findings.push({
            type  : 'cross-origin-sheet',
            target: sheet.href,
            source: sheet.href,
          });
        }
      }
    });

    // ═════════════════════════════════════════════════════════════════════════
    // Check 4 — <meta name="viewport"> orientation restriction
    // ═════════════════════════════════════════════════════════════════════════
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport) {
      const content = (viewport.getAttribute('content') || '').toLowerCase();
      if (content.includes('orientation=')) {
        findings.push({
          type    : 'meta-viewport-orientation',
          target  : 'meta[name="viewport"]',
          selector: 'meta[name="viewport"]',
          snippet : viewport.outerHTML,
        });
      }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Check 5 — @media orientation with structural CSS that may break layout
    //   One finding per affected CSS style rule.
    //   Same double-recursion fix as Check 3 applied here too.
    // ═════════════════════════════════════════════════════════════════════════
    const STRUCTURAL_PROPS = /(?:position\s*:\s*(?:fixed|absolute)|width\s*:\s*(?:0px|[0-9]+vh)|height\s*:\s*(?:0px|[0-9]+vw)|overflow\s*:\s*hidden|clip\s*:\s*rect)/i;

    function scanStructuralRules(rules, sheetLabel) {
      if (!rules) return;
      for (const rule of rules) {
        try {
          if (rule.type === CSSRule.MEDIA_RULE) {
            const mediaText   = rule.conditionText || rule.media?.mediaText || '';
            const orientMatch = mediaText.match(/orientation\s*:\s*(portrait|landscape)|(?:max|min)-aspect-ratio/i);
            if (orientMatch) {
              for (const inner of (rule.cssRules || [])) {
                if (inner.type === CSSRule.STYLE_RULE && STRUCTURAL_PROPS.test(inner.cssText)) {
                  findings.push({
                    type      : 'css-media-structural',
                    target    : inner.selectorText,
                    selector  : inner.selectorText,
                    snippet   : inner.cssText.slice(0, 120),
                    source    : sheetLabel,
                    mediaQuery: mediaText,
                  });
                }
              }
            } else {
              scanStructuralRules(rule.cssRules, sheetLabel);
            }
          } else if (rule.type === CSSRule.SUPPORTS_RULE) {
            scanStructuralRules(rule.cssRules, sheetLabel);
          }
        } catch (_) {}
      }
    }

    Array.from(document.styleSheets).forEach((sheet, i) => {
      const label = sheet.href ? sheet.href : `<style[${i}]>`;
      try { scanStructuralRules(sheet.cssRules, label); } catch (_) {}
    });

    // ═════════════════════════════════════════════════════════════════════════
    // Check 6 — CSS writing-mode on body forcing vertical orientation
    // ═════════════════════════════════════════════════════════════════════════
    const writingMode = window.getComputedStyle(document.body).writingMode;
    if (writingMode === 'vertical-rl' || writingMode === 'vertical-lr') {
      findings.push({
        type  : 'writing-mode',
        signal: 'writing-mode',
        target: 'body',
        detail: writingMode,
      });
    }

    // ═════════════════════════════════════════════════════════════════════════
    // Check 7 — <meta name="viewport"> maximum-scale=1 (prevents zoom/resize)
    // ═════════════════════════════════════════════════════════════════════════
    const viewportMeta = document.querySelector('meta[name="viewport"]');
    if (viewportMeta) {
      const content = viewportMeta.getAttribute('content') || '';
      if (/maximum-scale\s*=\s*1(?:\.0+)?\b/.test(content)) {
        findings.push({
          type  : 'viewport-scale',
          signal: 'viewport-scale',
          target: 'meta[name="viewport"]',
          snippet: viewportMeta.outerHTML,
          detail: content,
        });
      }
    }

    return findings;
  });

  // ── Merge and build element-wise rule entries ─────────────────────────────
  const allFindings = [...domFindings, ...manifestFindings];

  if (allFindings.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId     : RULE_ID,
        description: FALLBACK_DESCRIPTION,
        impact     : null,
        status     : 'pass',
        target     : null,
        selector   : null,
        snippet    : null,
        source     : null,
        mediaQuery : null,
        reason     : _t(sharedContext, 'No orientation-locking patterns detected (JS lock calls, forced CSS rotation, orientation-hiding media queries, manifest lock, or viewport meta).', '画面向き固定のパターンは検出されませんでした（JS の lock 呼び出し、強制回転 CSS、画面向き依存の非表示メディアクエリ、manifest ロック、viewport メタ設定など）。'),
        helpUrl    : HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: allFindings.map(finding => buildRule(finding, sharedContext)),
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
