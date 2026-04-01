'use strict';

const SC = '1.4.5';
const RULE_ID = 'custom-images-of-text';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/images-of-text';

// Logo/brand images are exempt from 1.4.5 (WCAG exception: logotypes)
const LOGO_PATTERN = /\b(logo|brand|wordmark|logotype|favicon)\b|ロゴ|ブランド/i;

// Patterns in alt, src path, or class/id that strongly suggest the image contains text
// rather than being a photo, diagram, or decorative graphic.
const TEXT_IMG_ALT_PATTERN = /^[\w\s,.:;!?'"()\-]{20,}$|"[^"]{10,}"|[A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+/;
const TEXT_IMG_SRC_PATTERN = /\/(banner|headline|text|quote|caption|ad|promo|slide|card|cta|announcement|copy|slogan|tagline|infographic|poster|flyer|screenshot|バナー|見出し|テキスト|引用|キャプション|広告|プロモ|カード|お知らせ|コピー|スローガン|ポスター|フライヤー|スクリーンショット)\b/i;
const TEXT_IMG_CLASS_PATTERN = /\b(banner|text-image|headline|quote|caption|promo|screenshot|infographic)\b|バナー|見出し|テキスト|キャプション|プロモ|インフォグラフィック/i;

// Minimum alt-text word count that suggests a meaningful textual description (image with text)
const MIN_WORDS_FOR_TEXT_IMAGE = 5;

async function run(page) {
  const data = await page.evaluate((params) => {
    const { logoPattern, srcPattern, classPattern, minWords } = params;
    const logoRe   = new RegExp(logoPattern, 'i');
    const srcRe    = new RegExp(srcPattern,  'i');
    const classRe  = new RegExp(classPattern,'i');

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
          html: img.outerHTML.slice(0, 200),
          id:   img.id || null,
        });
      } else if (score === 2) {
        needsReview.push({
          src:  src.slice(-80),
          alt:  alt.slice(0, 100),
          html: img.outerHTML.slice(0, 200),
          id:   img.id || null,
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
        html: el.outerHTML.slice(0, 200),
        id:   el.id || null,
      });
    }

    return { violations, needsReview, bgTextViolations, checkedCount };
  }, {
    logoPattern:  LOGO_PATTERN.source,
    srcPattern:   TEXT_IMG_SRC_PATTERN.source,
    classPattern: TEXT_IMG_CLASS_PATTERN.source,
    minWords:     MIN_WORDS_FOR_TEXT_IMAGE,
  });

  const allViolations = [
    ...(data.violations      || []),
    ...(data.bgTextViolations|| []),
  ];
  const reviews = data.needsReview || [];

  if (allViolations.length === 0 && reviews.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId:      RULE_ID,
        description: 'Images should not contain text unless the visual presentation is essential',
        impact:      null,
        status:      'pass',
        reason:      data.checkedCount > 0
          ? `${data.checkedCount} image(s) checked — no images detected as likely containing non-essential text. (OCR-level verification available via the Python pipeline.)`
          : 'No candidate images detected for 1.4.5 text-image check.',
        helpUrl: HELP_URL,
      }],
    };
  }

  if (allViolations.length > 0) {
    const sample = allViolations.slice(0, 3)
      .map(v => `<img src="…${v.src}" alt="${v.alt}">`)
      .join('; ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId:      RULE_ID,
        description: 'Images should not contain text unless the visual presentation is essential',
        impact:      'moderate',
        status:      'fail',
        reason:      `${allViolations.length} image(s) appear to contain non-essential text based on src path and alt-text heuristics: ${sample}. Use real HTML/CSS text instead of text baked into images.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  // Only needs_review items
  const sample = reviews.slice(0, 3)
    .map(v => `<img src="…${v.src}" alt="${v.alt}">`)
    .join('; ');
  return {
    successCriteriaId: SC,
    rules: [{
      ruleId:      RULE_ID,
      description: 'Images should not contain text unless the visual presentation is essential',
      impact:      'minor',
      status:      'incomplete',
      reason:      `${reviews.length} image(s) may contain text — manual or OCR verification recommended: ${sample}.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
