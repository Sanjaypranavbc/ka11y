'use strict';

/**
 * WCAG 1.1.1 Non-text Content — DOM-level techniques that axe-core does not cover.
 *
 *   ARIA6   aria-label on elements whose role prohibits naming, or empty aria-label
 *   H86     emoticons / ASCII art / emoji-only controls without a text alternative
 *   C18     spacer images that are not marked decorative
 *   H53     <object> whose fallback body is empty or is itself an image without alt
 *   H2      adjacent image link + text link to the same destination (should be one link)
 *   G143    CAPTCHA images must describe their purpose (custom CAPTCHAs, not only providers)
 *   G144    CAPTCHA must offer an alternative modality (audio); known providers ship one
 *   G68     live media must carry a descriptive accessible name
 */

const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC = '1.1.1';
const RULE_ID = 'custom-non-text-content';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/non-text-content';
const MODE = 'static';
const FALLBACK_DESCRIPTION = 'Non-text content must have a text alternative that serves the equivalent purpose';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

function _rule(status, impact, reason, elements) {
  const r = { ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact, status, reason, helpUrl: HELP_URL };
  if (elements && elements.length) r.elements = elements;
  return r;
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const raw = await page.evaluate(() => {
    const out = { issues: [], counts: { ariaLabelChecked: 0, images: 0, captchas: 0, objects: 0, liveMedia: 0 } };
    const sel = (el) => el.tagName.toLowerCase() + (el.id ? `#${CSS.escape(el.id)}` : '');
    const visible = (el) => {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 || r.height > 0;
    };
    const hiddenFromAT = (el) => !!el.closest('[aria-hidden="true"]');
    const accName = (el) => {
      const bits = [el.getAttribute('aria-label') || '', el.getAttribute('title') || ''];
      for (const id of (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) {
        const ref = document.getElementById(id);
        if (ref) bits.push(ref.textContent || '');
      }
      return bits.join(' ').replace(/\s+/g, ' ').trim();
    };
    const add = (type, el, detail, technique) => {
      out.issues.push({ type, technique, target: sel(el), snippet: el.outerHTML.slice(0, 160), detail });
    };

    // ── ARIA6: aria-label on elements that cannot carry a name, or empty ──────
    try {
      const NAME_PROHIBITED_TAGS = /^(div|span|p|section|article|aside|header|footer|main|nav|ul|ol|li|table|tbody|thead|tr|td|th|dl|dt|dd|blockquote|pre|code|em|strong|b|i|u|s|small|sub|sup|mark|abbr|cite|q|time|label|legend|caption|figure|figcaption|address|hr|br)$/;
      const NAME_PROHIBITED_ROLES = /^(caption|code|deletion|emphasis|generic|insertion|paragraph|presentation|none|strong|subscript|superscript)$/;
      let n = 0;
      for (const el of document.querySelectorAll('[aria-label]')) {
        if (n++ > 3000) break;
        out.counts.ariaLabelChecked++;
        const label = el.getAttribute('aria-label') || '';
        const role = (el.getAttribute('role') || '').toLowerCase();
        const tag = el.tagName.toLowerCase();
        if (!label.trim()) {
          add('empty-aria-label', el, 'aria-label is empty or whitespace — assistive technology exposes no name (ARIA6)', 'ARIA6');
          continue;
        }
        if (role && !NAME_PROHIBITED_ROLES.test(role)) continue; // explicit nameable role
        if (role && NAME_PROHIBITED_ROLES.test(role)) {
          add('aria-label-prohibited-role', el, `aria-label on role="${role}" is ignored by assistive technology (naming prohibited)`, 'ARIA6');
          continue;
        }
        const focusable = el.hasAttribute('tabindex') || el.isContentEditable;
        if (!role && NAME_PROHIBITED_TAGS.test(tag) && !focusable && !['table', 'figure', 'section', 'article', 'aside', 'nav', 'header', 'footer', 'main', 'hr'].includes(tag)) {
          add('aria-label-generic-element', el, `aria-label on a <${tag}> with no role is not exposed as a name by screen readers — use role="img"/a landmark role, visible text, or move the label to the control (ARIA6)`, 'ARIA6');
        }
        if (out.issues.length > 60) break;
      }
    } catch (_) { /* section must not break the check */ }

    // ── H86: emoticons, ASCII art, emoji-only controls ────────────────────────
    try {
      const EMOTICON_RE = /(?:^|\s)(?:[:;=8xX][-o^']?[)(DPp|\/\\O3*]|[)(D|][-o^']?[:;=8]|\^_\^|\^-\^|>_<|T_T|;_;|o_O|O_o|\(\^\^\)|\(\^_\^\)|\(T_T\)|m\(_ _\)m|orz|¯\\_\(ツ\)_\/¯|\(╯°□°\)╯)(?=\s|$|[.,!?])/;
      let EMOJI_RE = null;
      try { EMOJI_RE = new RegExp('\\p{Extended_Pictographic}', 'u'); } catch (_) { EMOJI_RE = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u; }
      // ASCII art: <pre> blocks of ≥3 lines with symbol-dense content
      for (const pre of document.querySelectorAll('pre')) {
        if (hiddenFromAT(pre) || !visible(pre)) continue;
        const text = pre.textContent || '';
        const lines = text.split('\n').filter(l => l.trim().length > 2);
        if (lines.length < 3) continue;
        const symbols = (text.match(/[^\w\s぀-ヿ㐀-鿿]/g) || []).length;
        const letters = (text.match(/[\w぀-ヿ㐀-鿿]/g) || []).length;
        if (symbols >= 30 && symbols > letters * 1.5) {
          const named = pre.getAttribute('role') === 'img' && accName(pre);
          if (!named) add('ascii-art-no-alternative', pre, 'Block looks like ASCII art; wrap it in role="img" with aria-label (or aria-hidden it and add a text description) so screen readers do not read every symbol (H86)', 'H86');
        }
      }
      // Emoticons in visible text (limit scan)
      let scanned = 0;
      for (const el of document.querySelectorAll('p, li, td, span, div, h1, h2, h3, h4, h5, h6, figcaption, blockquote')) {
        if (scanned++ > 2500) break;
        if (el.children.length > 6) continue;
        const text = (el.textContent || '');
        if (text.length > 400 || text.length < 2) continue;
        if (!EMOTICON_RE.test(text)) continue;
        if (hiddenFromAT(el) || !visible(el)) continue;
        if (el.closest('[role="img"][aria-label], abbr[title]')) continue;
        add('emoticon-no-alternative', el, `Text contains an emoticon (${(text.match(EMOTICON_RE) || [''])[0].trim()}) with no text alternative — use <abbr title> or role="img" + aria-label (H86)`, 'H86');
        if (out.issues.length > 80) break;
      }
      // Controls whose only content is emoji/pictographs and that have no accessible name
      for (const el of document.querySelectorAll('a[href], button, [role="button"], [role="link"], [role="tab"], [role="menuitem"]')) {
        if (hiddenFromAT(el) || !visible(el)) continue;
        const text = (el.textContent || '').replace(/\s+/g, '');
        if (!text || text.length > 6) continue;
        const stripped = text.replace(/[️‍]/g, '');
        if (!EMOJI_RE.test(stripped)) continue;
        const rest = stripped.replace(/\p{Extended_Pictographic}/gu, '').replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '');
        if (rest.length) continue; // has real text too
        if (accName(el) || el.querySelector('img[alt], svg title, [aria-label]')) continue;
        add('emoji-only-control', el, 'Control is labelled only by an emoji; screen readers announce the Unicode name, which rarely describes the action — add aria-label or visible text (H86)', 'H86');
      }
    } catch (_) { /* ignore */ }

    // ── C18: spacer images ───────────────────────────────────────────────────
    try {
      const SPACER_SRC = /(^|[\/_.-])(spacer|blank|clear|transparent|pixel|shim|1x1|dot|empty)([\/_.-]|\.(gif|png)|$)/i;
      for (const img of document.querySelectorAll('img')) {
        out.counts.images++;
        const src = img.getAttribute('src') || '';
        const w = img.naturalWidth || parseInt(img.getAttribute('width') || '0', 10);
        const h = img.naturalHeight || parseInt(img.getAttribute('height') || '0', 10);
        const tiny = (w > 0 && w <= 2 && h > 0 && h <= 2);
        const named = SPACER_SRC.test(src);
        if (!tiny && !named) continue;
        if (/^data:/.test(src) && !tiny) continue;
        const alt = img.getAttribute('alt');
        const decorative = alt === '' || img.getAttribute('role') === 'presentation' || img.getAttribute('role') === 'none' || hiddenFromAT(img);
        if (decorative) continue;
        add('spacer-image-not-decorative', img, `Spacer/transparent image (${w}×${h}px${named ? ', src suggests spacer' : ''}) must be marked decorative with alt="" — better, replace it with CSS margin/padding (C18)`, 'C18');
        if (out.issues.length > 100) break;
      }
    } catch (_) { /* ignore */ }

    // ── H53: <object> fallback content ────────────────────────────────────────
    try {
      for (const obj of document.querySelectorAll('object')) {
        out.counts.objects++;
        if (hiddenFromAT(obj)) continue;
        if (accName(obj)) continue;
        const fallbackText = Array.from(obj.childNodes).filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'PARAM')).map(n => (n.textContent || '').trim()).join(' ').trim();
        const fallbackImgs = Array.from(obj.querySelectorAll('img'));
        const badImgs = fallbackImgs.filter(i => !(i.getAttribute('alt') || '').trim());
        if (!fallbackText && (!fallbackImgs.length || badImgs.length)) {
          add('object-empty-fallback', obj, badImgs.length
            ? 'The <object> fallback is an image without alt text — the fallback itself has no text alternative (H53)'
            : '<object> has no accessible name and no fallback text between its tags (H53)', 'H53');
        }
      }
    } catch (_) { /* ignore */ }

    // ── H2: adjacent image link + text link to the same href ─────────────────
    try {
      const links = Array.from(document.querySelectorAll('a[href]')).filter(a => !hiddenFromAT(a) && visible(a));
      const isImgOnly = (a) => {
        const text = (a.textContent || '').trim();
        return !text && a.querySelector('img, svg, picture');
      };
      const nextLink = (a) => {
        // Walk forward through siblings/parents to the next anchor, ignoring whitespace-only nodes.
        let n = a;
        for (let hops = 0; hops < 4 && n; hops++) {
          let s = n.nextSibling;
          while (s && ((s.nodeType === 3 && !s.textContent.trim()) || (s.nodeType === 1 && s.tagName === 'BR'))) s = s.nextSibling;
          if (s && s.nodeType === 1) {
            if (s.tagName === 'A') return s;
            const inner = s.querySelector('a[href]');
            if (inner && s.textContent.trim() === inner.textContent.trim()) return inner;
            return null;
          }
          if (s && s.nodeType === 3 && s.textContent.trim()) return null;
          n = n.parentElement;
          if (!n || /^(LI|TD|TH|SECTION|ARTICLE|MAIN|BODY|UL|OL|NAV)$/.test(n.tagName)) return null;
        }
        return null;
      };
      let pairs = 0;
      for (const a of links) {
        const b = nextLink(a);
        if (!b || b === a) continue;
        if (a.href !== b.href) continue;
        const aImg = isImgOnly(a), bImg = isImgOnly(b);
        if (aImg === bImg) continue;
        const imgLink = aImg ? a : b;
        const img = imgLink.querySelector('img');
        const imgAlt = img ? (img.getAttribute('alt') || '') : (accName(imgLink) || '');
        const textLink = aImg ? b : a;
        const same = imgAlt.trim().toLowerCase() === (textLink.textContent || '').trim().toLowerCase();
        add('adjacent-duplicate-links', a, same
          ? 'Adjacent image link and text link go to the same destination with the same name — screen reader users hear the link twice; combine into one <a> (H2)'
          : `Adjacent image link (alt "${imgAlt.slice(0, 40)}") and text link "${(textLink.textContent || '').trim().slice(0, 40)}" share a destination — combine into one <a> with alt="" on the image (H2)`, 'H2');
        if (++pairs >= 15) break;
      }
    } catch (_) { /* ignore */ }

    // ── G143 / G144: CAPTCHA purpose and alternative modality ────────────────
    try {
      const PROVIDER_RE = /recaptcha|hcaptcha|turnstile|cloudflare\.com\/turnstile|funcaptcha|arkoselabs|geetest|mtcaptcha|friendlycaptcha/i;
      const CAPTCHA_WORD = /captcha|verification\s*code|security\s*code|認証コード|画像認証|セキュリティコード/i;
      const AUDIO_WORD = /audio|listen|sound|音声|読み上げ/i;
      const providers = Array.from(document.querySelectorAll('iframe[src], div[class], div[id], script[src]')).filter(el =>
        PROVIDER_RE.test(el.getAttribute('src') || '') || PROVIDER_RE.test(el.className || '') || PROVIDER_RE.test(el.id || ''));
      if (providers.length) out.counts.captchas++;
      // Custom CAPTCHA images: img near an input whose name/id/placeholder mentions captcha/code, or alt/src mentions captcha
      const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(i =>
        CAPTCHA_WORD.test([i.name, i.id, i.placeholder, i.getAttribute('aria-label'), i.getAttribute('autocomplete')].join(' ')));
      const candidates = new Set();
      for (const img of document.querySelectorAll('img, canvas, svg')) {
        const alt = img.getAttribute('alt') || '';
        const src = img.getAttribute('src') || '';
        if (CAPTCHA_WORD.test(alt) || CAPTCHA_WORD.test(src) || CAPTCHA_WORD.test(img.className || '') || CAPTCHA_WORD.test(img.id || '')) candidates.add(img);
      }
      for (const input of inputs) {
        const scope = input.closest('form, fieldset, div') || document.body;
        for (const img of scope.querySelectorAll('img, canvas, svg')) {
          const r1 = input.getBoundingClientRect(), r2 = img.getBoundingClientRect();
          if (Math.abs(r1.top - r2.top) < 200) candidates.add(img);
        }
      }
      for (const img of candidates) {
        if (hiddenFromAT(img)) continue;
        if (img.closest('[class*="captcha" i], [id*="captcha" i]') && PROVIDER_RE.test(img.closest('[class*="captcha" i], [id*="captcha" i]').outerHTML.slice(0, 400))) continue;
        out.counts.captchas++;
        const name = img.tagName === 'IMG' ? (img.getAttribute('alt') || '') : accName(img);
        if (!name.trim() || !CAPTCHA_WORD.test(name)) {
          add('captcha-purpose-not-described', img, `CAPTCHA image alt text ("${name.slice(0, 40)}") must describe its purpose, e.g. "Type the characters shown in the image" — never the answer (G143)`, 'G143');
        }
        const scope = img.closest('form, fieldset, section, div') || document.body;
        const hasAudio = Array.from(scope.querySelectorAll('a, button, [role="button"], audio, [aria-label], [title]')).some(el =>
          AUDIO_WORD.test((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')));
        if (!hasAudio) {
          add('captcha-no-alternative-modality', img, 'Visual CAPTCHA with no audio (or other non-visual) alternative detected nearby — blind users cannot complete it (G144)', 'G144');
        }
      }
      if (providers.length && !candidates.size) {
        // Known providers (reCAPTCHA v2, hCaptcha, Turnstile) ship an audio/accessible challenge — pass with note.
        out.counts.providerCaptcha = providers.length;
      }
    } catch (_) { /* ignore */ }

    // ── G68: live media needs a descriptive accessible name ──────────────────
    try {
      const LIVE_RE = /\.m3u8|\.mpd|\/live\/|live[-_]?stream|livestream|is[-_]?live|\blive\b|ライブ|生放送|生配信/i;
      for (const media of document.querySelectorAll('video, audio, iframe')) {
        const src = media.getAttribute('src') || (media.querySelector && media.querySelector('source') ? media.querySelector('source').getAttribute('src') : '') || '';
        const markers = [src, media.className || '', media.id || '', media.getAttribute('data-live') || ''].join(' ');
        if (!LIVE_RE.test(markers)) continue;
        if (hiddenFromAT(media)) continue;
        out.counts.liveMedia++;
        let name = accName(media);
        if (!name) {
          const fig = media.closest('figure');
          const cap = fig && fig.querySelector('figcaption');
          if (cap) name = (cap.textContent || '').trim();
        }
        if (!name) {
          let prev = media.parentElement;
          for (let i = 0; i < 3 && prev && !name; i++) {
            const h = prev.querySelector('h1, h2, h3, h4');
            if (h) name = (h.textContent || '').trim();
            prev = prev.parentElement;
          }
        }
        if (!name || name.length < 4) {
          add('live-media-no-name', media, 'Live audio/video has no descriptive label (aria-label, title, figcaption or nearby heading) identifying what the live content is (G68)', 'G68');
        }
      }
    } catch (_) { /* ignore */ }

    return out;
  });

  const data = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : { issues: [], counts: {} };
  const issues = Array.isArray(data.issues) ? data.issues : [];

  if (!issues.length) {
    const c = data.counts || {};
    return {
      successCriteriaId: SC,
      rules: [_rule('pass', null, _t(ctx,
        'No non-text content issues detected beyond axe rules ({labels} aria-label(s), {imgs} image(s), {objs} object(s) inspected; emoticons/ASCII art, spacer images, adjacent duplicate links, CAPTCHA purpose and live-media naming all clear{prov}).',
        'axe ルール以外の非テキストコンテンツの問題は検出されませんでした（aria-label {labels} 件、画像 {imgs} 件、object {objs} 件を確認。顔文字/アスキーアート、スペーサー画像、隣接する重複リンク、CAPTCHA の目的、ライブメディアの名前はすべて問題なし{prov}）。',
        { labels: c.ariaLabelChecked || 0, imgs: c.images || 0, objs: c.objects || 0, prov: c.providerCaptcha ? _t(ctx, '; a third-party CAPTCHA provider with a built-in audio alternative is present', '。音声代替を備えたサードパーティ CAPTCHA が存在します') : '' }))],
    };
  }

  const FAIL_TYPES = new Set(['empty-aria-label', 'aria-label-prohibited-role', 'spacer-image-not-decorative', 'object-empty-fallback', 'captcha-purpose-not-described', 'emoji-only-control']);
  const fails = issues.filter(i => FAIL_TYPES.has(i.type));
  const reviews = issues.filter(i => !FAIL_TYPES.has(i.type));
  const rules = [];
  const summarize = (list) => [...new Set(list.map(i => `${i.technique}:${i.type}`))].join(', ');

  if (fails.length) {
    rules.push(_rule('fail', 'serious', _t(ctx,
      '{n} non-text content failure(s): {types}. Each element needs a proper text alternative (or alt="" when purely decorative).',
      '{n} 件の非テキストコンテンツの不備があります: {types}。各要素に適切なテキスト代替（純粋に装飾的な場合は alt=""）が必要です。',
      { n: fails.length, types: summarize(fails) }), fails));
  }
  if (reviews.length) {
    rules.push({ ..._rule('incomplete', 'moderate', _t(ctx,
      '{n} item(s) need review: {types}. Emoticons/ASCII art need a text alternative, adjacent duplicate links should be combined, and CAPTCHAs need a non-visual alternative.',
      '{n} 件の確認が必要です: {types}。顔文字/アスキーアートにはテキスト代替が必要で、隣接する重複リンクは 1 つに統合し、CAPTCHA には視覚以外の代替手段が必要です。',
      { n: reviews.length, types: summarize(reviews) }), reviews), ruleId: `${RULE_ID}-review` });
  }
  return { successCriteriaId: SC, rules };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
