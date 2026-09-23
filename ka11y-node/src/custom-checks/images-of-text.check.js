'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '1.4.5';
const RULE_ID = 'custom-images-of-text';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/images-of-text';

// Logo/brand images are exempt from 1.4.5 (WCAG exception: logotypes)
const MIN_WORDS_FOR_TEXT_IMAGE = 5;

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const logoPattern = buildKeywordPattern(
    getKeywordList('images_of_text', 'logo_keywords', sharedContext)
  );

  const textKeywordPattern = buildKeywordPattern(
    getKeywordList('images_of_text', 'text_keywords', sharedContext)
  );

  const data = await page.evaluate((params) => {
    const { logoPattern, textKeywordPattern, minWords } = params;
    const logoRe   = new RegExp(logoPattern, 'i');
    const srcRe    = new RegExp(textKeywordPattern,  'i');
    const classRe  = new RegExp(textKeywordPattern,'i');

    const violations    = [];
    const needsReview   = [];
    let   checkedCount  = 0;

    for (const img of document.querySelectorAll('img[src]')) {
      const src      = img.getAttribute('src')  || '';
      let decodedSrc = src;
      try {
        decodedSrc = decodeURIComponent(src);
      } catch (_) {}
      const alt      = (img.getAttribute('alt') || '').trim();
      const classStr = (img.className            || '');
      const idStr    = (img.id                   || '');
      const role     = (img.getAttribute('role') || '').toLowerCase();

      // Skip decorative (empty alt), hidden, or role="presentation"
      if (alt === '' || role === 'presentation' || role === 'none') continue;
      // Skip logos (WCAG 1.4.5 logotype exemption)
      if (logoRe.test(alt) || logoRe.test(src) || logoRe.test(decodedSrc) || logoRe.test(idStr) || logoRe.test(classStr)) continue;

      checkedCount++;

      const altWordCount = alt.split(/\s+/).filter(Boolean).length;
      const hasCjk = /[\u3040-\u30ff\u3400-\u9fff]/.test(alt);

      // Strong signal: src path suggests a text-image
      const srcSignal   = srcRe.test(src) || srcRe.test(decodedSrc);
      // Medium signal: class/id suggests text-image
      const classSignal = classRe.test(classStr) || classRe.test(idStr);
      // Medium signal: alt describes multiple words of text (looks like a caption, not a description)
      const longAlt     = hasCjk ? alt.length >= 8 : altWordCount >= minWords;
      // Weak signal: alt looks like a sentence (capitals + punctuation, no spaces in src filename)
      const altSentence = /[.!?。！？]$/.test(alt) || (/^[A-Z]/.test(alt) && altWordCount >= 4) || (hasCjk && alt.length >= 12);

      const score = (srcSignal ? 2 : 0) + (classSignal ? 1 : 0) + (longAlt ? 1 : 0) + (altSentence ? 1 : 0);

      if (score >= 3) {
        violations.push({
          src:  src.slice(-80),
          alt:  alt.slice(0, 100),
          html: img.outerHTML.slice(0, 150),
          element_id: img.id || null,
          target: img.id ? [`img#${CSS.escape(img.id)}`] : ['img[src]'],
          tag: 'IMG',
        });
      } else if (score === 2) {
        needsReview.push({
          src:  src.slice(-80),
          alt:  alt.slice(0, 100),
          html: img.outerHTML.slice(0, 150),
          element_id: img.id || null,
          target: img.id ? [`img#${CSS.escape(img.id)}`] : ['img[src]'],
          tag: 'IMG',
        });
      }
    }

    // Also check CSS background images on elements that contain text content
    const bgTextViolations = [];
    const bgCandidates = document.querySelectorAll('[style*="background-image"], [class*="bg-"], [class*="background"]');
    for (const el of bgCandidates) {
      const cs = window.getComputedStyle(el);
      if (!cs.backgroundImage || cs.backgroundImage === 'none') continue;
      const text = (el.textContent || '').trim();
      // If element has background image AND contains substantial visible text, it's a potential text image
      if (text.length < 10) continue;
      // Check if the background image url looks like a text-image source
      if (!srcRe.test(cs.backgroundImage)) continue;
      bgTextViolations.push({
        src:  cs.backgroundImage.slice(0, 80),
        text: text.slice(0, 60),
        html: el.outerHTML.slice(0, 150),
        element_id: el.id || null,
        target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()],
        tag: el.tagName.toUpperCase(),
      });
    }

    // SVG <text> elements used as images
    const svgTextViolations = [];
    for (const svg of document.querySelectorAll('svg')) {
      const textEls = svg.querySelectorAll('text');
      if (textEls.length > 0 && svg.closest('a, button, [role="img"], figure')) {
        svgTextViolations.push({
          type: 'svg-text-image',
          html: svg.outerHTML.slice(0, 150),
          element_id: svg.id || null,
          target: svg.id ? [`svg#${CSS.escape(svg.id)}`] : ['svg'],
          tag: 'SVG',
        });
      }
    }

    // C30: CSS image-replacement of real text (text-indent:-9999px, clip, transparent
    // colour over a background image). This is an image of text; C30 allows it only when
    // a control lets the user switch to the real text.
    const cssReplacementViolations = [];
    const cssReplacementWithToggle = [];
    try {
      const TOGGLE_RE = /text\s*(?:version|only|view|mode)|show\s+text|display\s+text|hide\s+images?|テキスト(?:表示|版|のみ)|画像を(?:非表示|隠す)/i;
      const hasToggle = Array.from(document.querySelectorAll('button, a[href], [role="button"], input[type="checkbox"], [role="switch"]')).some(el => TOGGLE_RE.test((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')));
      let scanned = 0;
      for (const el of document.querySelectorAll('h1, h2, h3, h4, h5, h6, a, span, div, p, li')) {
        if (scanned++ > 3000 || cssReplacementViolations.length + cssReplacementWithToggle.length >= 15) break;
        const text = (el.textContent || '').trim();
        if (text.length < 2 || text.length > 80 || el.children.length > 1) continue;
        const cs = window.getComputedStyle(el);
        const indent = parseFloat(cs.textIndent);
        const clipped = cs.clip && cs.clip !== 'auto' && /rect\(0(?:px)?,?\s*0(?:px)?,?\s*0(?:px)?,?\s*0(?:px)?\)/.test(cs.clip);
        const hasBg = cs.backgroundImage !== 'none' || !!el.querySelector('img, svg') || (el.parentElement && window.getComputedStyle(el.parentElement).backgroundImage !== 'none');
        const replaced = (indent <= -999 && hasBg) || (clipped && hasBg) || (cs.fontSize === '0px' && hasBg) || (cs.color === 'rgba(0, 0, 0, 0)' && hasBg);
        if (!replaced) continue;
        if (logoRe.test(text) || logoRe.test(el.className || '') || logoRe.test(el.id || '')) continue;
        const entry = { type: 'css-image-replacement', text: text.slice(0, 60), html: el.outerHTML.slice(0, 150), element_id: el.id || null, target: el.id ? [`${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`] : [el.tagName.toLowerCase()], tag: el.tagName.toUpperCase(), hasToggle };
        (hasToggle ? cssReplacementWithToggle : cssReplacementViolations).push(entry);
      }
    } catch (_) { /* ignore */ }

    // C22: text drawn onto <canvas> (recorded by the runtime fillText/strokeText hook)
    // without an accessible text equivalent (aria-label or fallback content).
    const canvasTextViolations = [];
    try {
      const R = window.__ka11yRuntime;
      if (R && typeof R.canvasTextOf === 'function') {
        for (const c of document.querySelectorAll('canvas')) {
          const drawn = R.canvasTextOf(c);
          if (!drawn || drawn.replace(/\s+/g, '').length < 4) continue;
          const r = c.getBoundingClientRect();
          if (r.width < 40 || r.height < 20) continue;
          const name = ((c.getAttribute('aria-label') || '') + ' ' + (c.textContent || '')).trim();
          if (name.length >= Math.min(drawn.length, 20) * 0.5) continue;
          canvasTextViolations.push({ type: 'canvas-text', text: drawn.slice(0, 60), html: c.outerHTML.slice(0, 150), element_id: c.id || null, target: c.id ? [`canvas#${CSS.escape(c.id)}`] : ['canvas'], tag: 'CANVAS' });
          if (canvasTextViolations.length >= 10) break;
        }
      }
    } catch (_) { /* ignore */ }

    return { violations, needsReview, bgTextViolations, svgTextViolations, cssReplacementViolations, cssReplacementWithToggle, canvasTextViolations, checkedCount };
  }, {
    logoPattern,
    textKeywordPattern,
    minWords: MIN_WORDS_FOR_TEXT_IMAGE,
  });

  const allViolations = [
    ...(data.violations      || []),
    ...(data.bgTextViolations|| []),
    ...(data.svgTextViolations|| []),
    ...(data.cssReplacementViolations || []),
    ...(data.canvasTextViolations || []),
  ];
  // C30: image replacement with a text/image toggle control is the permitted pattern — review only.
  const reviews = [...(data.needsReview || []), ...(data.cssReplacementWithToggle || [])];

  if (allViolations.length === 0 && reviews.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId:      RULE_ID,
        description: 'Images should not contain text unless the visual presentation is essential',
        impact:      null,
        status:      'pass',
        reason:      data.checkedCount > 0
          ? _t(sharedContext, '{count} image(s) checked — no images detected as likely containing non-essential text. (OCR-level verification available via the Python pipeline.)', '画像 {count} 件を確認しましたが、本質的でないテキストを含む可能性が高い画像は検出されませんでした。（OCR レベルの検証は Python パイプラインで利用できます。）', { count: data.checkedCount })
          : _t(sharedContext, 'No candidate images detected for 1.4.5 text-image check.', '1.4.5 の画像内テキスト確認の対象となる画像は検出されませんでした。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (allViolations.length > 0) {
    const sample = allViolations.slice(0, 3)
      .map(v => v.type === 'svg-text-image'
        ? `<svg with text> ${v.html.slice(0, 60)}`
        : v.type === 'css-image-replacement'
          ? `CSS image replacement of "${v.text}" (C30 — no text/image toggle)`
          : v.type === 'canvas-text'
            ? `<canvas> draws text "${v.text}" with no text equivalent (C22)`
            : `<img src="…${v.src}" alt="${v.alt}">`)
      .join('; ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId:      RULE_ID,
        description: 'Images should not contain text unless the visual presentation is essential',
        impact:      'moderate',
        status:      'incomplete',
        reason:      _t(sharedContext, '{count} image(s) appear to contain non-essential text based on src path and alt-text heuristics: {sample}. Manual or OCR verification required to confirm if text is essential.', 'src パスと alt テキストのヒューリスティクスに基づき、本質的でないテキストを含む可能性がある画像が {count} 件検出されました: {sample}。テキストが本質的かどうか、手動または OCR による確認が必要です。', { count: allViolations.length, sample }),
        elements: allViolations,
        helpUrl: HELP_URL,
      }],
    };
  }

  // Only needs_review items
  const sample = reviews.slice(0, 3)
    .map(v => v.type === 'css-image-replacement' ? `CSS image replacement of "${v.text}" — a text-version toggle exists (C30)` : `<img src="…${v.src}" alt="${v.alt}">`)
    .join('; ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId:      RULE_ID,
      description: 'Images should not contain text unless the visual presentation is essential',
      impact:      'minor',
      status:      'incomplete',
      reason:      _t(sharedContext, '{count} image(s) may contain text — manual or OCR verification recommended: {sample}.', 'テキストを含む可能性がある画像が {count} 件あります。目視または OCR による確認を推奨します: {sample}。', { count: reviews.length, sample }),
      elements: reviews,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
