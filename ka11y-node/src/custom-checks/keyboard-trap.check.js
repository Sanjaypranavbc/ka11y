'use strict';

const SC = '2.1.2';
const RULE_ID = 'custom-keyboard-trap';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap';
const MAX_TABS = 200;
// Buffer size for cycle detection: tracks last 4 focused keys.
// This detects both single-element stuck traps (A,A,A) and two-element cycling
// traps (A,B,A,B) — the most common real-world pattern (dialog with 2 focusable elements).
const CYCLE_WINDOW = 4;
// Settle delay: allow focus event handlers and page mutations to complete before reading state
const SETTLE_MS = 60;

async function run(page) {
  // Focus the page body to start from a known position
  await page.evaluate(() => { try { document.body.focus(); } catch (_) {} });

  // Bug fix: track the LAST N focus targets to detect consecutive repetition
  // rather than cumulative count which caused false positives on identical elements
  const recentKeys = [];
  let trapHtml = null;

  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press('Tab');
    // Wait for focus event handlers and React/Vue re-renders to settle
    await new Promise(r => setTimeout(r, SETTLE_MS));

    const activeInfo = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      // Bug fix: prefer stable identifiers (id, name, aria-label) over DOM position.
      // Fall back to position+tag only when no stable attribute is available.
      const allEls = Array.from(document.querySelectorAll('*'));
      const pos = allEls.indexOf(el);
      // Use only id or name as stable key — NOT aria-label, which is often shared across
      // multiple elements (e.g. three "Close" buttons) and would produce false-positive traps.
      const stable = el.id || el.getAttribute('name') || '';
      const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
    });

    if (!activeInfo) break; // focus left the page or hit body

    recentKeys.push(activeInfo.key);
    if (recentKeys.length > CYCLE_WINDOW) recentKeys.shift();

    // Detect two trap patterns:
    // 1. Stuck: same element focused 3+ times consecutively (1-element trap)
    const isStuck = recentKeys.length >= 3 && recentKeys.every(k => k === recentKeys[0]);
    // 2. Two-element cycle: A→B→A→B (most common dialog/tooltip trap)
    const n = recentKeys.length;
    const isTwoElemCycle = n >= 4 &&
      recentKeys[n - 1] === recentKeys[n - 3] &&
      recentKeys[n - 2] === recentKeys[n - 4] &&
      recentKeys[n - 1] !== recentKeys[n - 2];
    const isConsecutiveTrap = isStuck || isTwoElemCycle;

    if (isConsecutiveTrap) {
      // Verify it's a real trap: try Escape then Tab
      // Settle after Escape to allow modal-close / focus-restore handlers to run
      await page.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, SETTLE_MS));
      await page.keyboard.press('Tab');
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const afterEscape = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || el.getAttribute('aria-label') || '';
        return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
      });

      if (afterEscape === activeInfo.key) {
        trapHtml = activeInfo.html;
        break;
      }
      // Escape worked — reset tracking and continue
      recentKeys.length = 0;
    }
  }

  // FN fix: also test Shift+Tab (backward) navigation for traps.
  // A trap may only manifest when tabbing backward through the component.
  // Puppeteer helper: 'Shift+Tab' is not a valid key name — use down/press/up.
  const shiftTab = async () => {
    await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    await page.keyboard.up('Shift');
  };

  if (!trapHtml) {
    const recentShiftKeys = [];

    for (let i = 0; i < MAX_TABS; i++) {
      await shiftTab();
      await new Promise(r => setTimeout(r, SETTLE_MS));

      const activeInfo = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body || el === document.documentElement) return null;
        const allEls = Array.from(document.querySelectorAll('*'));
        const pos = allEls.indexOf(el);
        const stable = el.id || el.getAttribute('name') || '';
        const key = stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        return { key, html: el.outerHTML.slice(0, 150), tagName: el.tagName.toLowerCase() };
      });

      if (!activeInfo) break;

      recentShiftKeys.push(activeInfo.key);
      if (recentShiftKeys.length > CYCLE_WINDOW) recentShiftKeys.shift();

      const sn = recentShiftKeys.length;
      const isShiftStuck = sn >= 3 && recentShiftKeys.every(k => k === recentShiftKeys[0]);
      const isShiftTwoElemCycle = sn >= 4 &&
        recentShiftKeys[sn - 1] === recentShiftKeys[sn - 3] &&
        recentShiftKeys[sn - 2] === recentShiftKeys[sn - 4] &&
        recentShiftKeys[sn - 1] !== recentShiftKeys[sn - 2];
      const isConsecutiveTrap = isShiftStuck || isShiftTwoElemCycle;

      if (isConsecutiveTrap) {
        // Verify: try Escape then Shift+Tab
        await page.keyboard.press('Escape');
        await new Promise(r => setTimeout(r, SETTLE_MS));
        await shiftTab();
        await new Promise(r => setTimeout(r, SETTLE_MS));

        const afterEscape = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          const pos = allEls.indexOf(el);
          const stable = el.id || el.getAttribute('name') || '';
          return stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`;
        });

        if (afterEscape === activeInfo.key) {
          trapHtml = activeInfo.html;
          break;
        }
        recentShiftKeys.length = 0;
      }
    }
  }

  // ── Arrow key trap detection in ARIA widgets ──────────────────────────────
  const arrowTrapRoles = ['tree', 'grid', 'listbox', 'menu', 'tablist', 'radiogroup'];
  const arrowTrapFindings = [];

  if (!trapHtml) {
    for (const role of arrowTrapRoles) {
      const widgets = await page.evaluate((r) => {
        return Array.from(document.querySelectorAll(`[role="${r}"]`)).slice(0, 3).map(el => ({
          id: el.id || null,
          html: el.outerHTML.slice(0, 100),
          selector: el.id ? `#${el.id}` : null,
          role: r,
        }));
      }, role);

      for (const widget of (widgets || [])) {
        // Focus the widget
        await page.evaluate((sel, r) => {
          const el = sel
            ? document.querySelector(sel)
            : document.querySelector(`[role="${r}"]`);
          if (el) el.focus({ preventScroll: true });
        }, widget.selector, role);
        await new Promise(res => setTimeout(res, SETTLE_MS));

        const before = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          return `${allEls.indexOf(el)}:${el.tagName}`;
        });

        // Press ArrowDown twice
        await page.keyboard.press('ArrowDown');
        await new Promise(res => setTimeout(res, SETTLE_MS));
        await page.keyboard.press('ArrowDown');
        await new Promise(res => setTimeout(res, SETTLE_MS));

        const after = await page.evaluate(() => {
          const el = document.activeElement;
          if (!el) return null;
          const allEls = Array.from(document.querySelectorAll('*'));
          return `${allEls.indexOf(el)}:${el.tagName}`;
        });

        if (before && after && before === after) {
          arrowTrapFindings.push({ type: 'arrow-key-trap', role, html: widget.html });
        }
      }
    }
  }

  // ── Same-origin iframe Tab trap detection ─────────────────────────────────
  const iframeTrapFindings = [];

  if (!trapHtml) {
    const frames = page.frames().filter(f => f !== page.mainFrame());
    for (const frame of frames) {
      try {
        // Try a basic Tab-trap detection in the frame (forward only, 30 iterations)
        const frameRecentKeys = [];
        let frameTrapHtml = null;

        await frame.evaluate(() => {
          try { document.body.focus(); } catch (_) {}
        });

        for (let i = 0; i < 30; i++) {
          await page.keyboard.press('Tab');
          await new Promise(res => setTimeout(res, SETTLE_MS));

          const frameActive = await frame.evaluate(() => {
            const el = document.activeElement;
            if (!el || el === document.body || el === document.documentElement) return null;
            const allEls = Array.from(document.querySelectorAll('*'));
            const pos = allEls.indexOf(el);
            const stable = el.id || el.getAttribute('name') || '';
            return { key: stable ? `${el.tagName}:${stable}` : `${pos}:${el.tagName}`, html: el.outerHTML.slice(0, 100) };
          }).catch(() => null);

          if (!frameActive) break;

          frameRecentKeys.push(frameActive.key);
          if (frameRecentKeys.length > CYCLE_WINDOW) frameRecentKeys.shift();

          const fn = frameRecentKeys.length;
          const frameStuck = fn >= 3 && frameRecentKeys.every(k => k === frameRecentKeys[0]);
          const frameCycle = fn >= 4 &&
            frameRecentKeys[fn - 1] === frameRecentKeys[fn - 3] &&
            frameRecentKeys[fn - 2] === frameRecentKeys[fn - 4] &&
            frameRecentKeys[fn - 1] !== frameRecentKeys[fn - 2];

          if (frameStuck || frameCycle) {
            frameTrapHtml = frameActive.html;
            break;
          }
        }

        if (frameTrapHtml) {
          iframeTrapFindings.push({ html: frameTrapHtml, frameUrl: frame.url() });
        }
      } catch (_) {
        // Cross-origin frame — skip
      }
    }
  }

  if (!trapHtml && arrowTrapFindings.length === 0 && iframeTrapFindings.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: 'Keyboard focus must not be trapped in a component', impact: null, status: 'pass', reason: 'No keyboard focus traps detected during Tab navigation.', helpUrl: HELP_URL }],
    };
  }

  if (!trapHtml) {
    const arrowDetail = arrowTrapFindings.map(f => `arrow-key trap in [role="${f.role}"]`).join('; ');
    const iframeDetail = iframeTrapFindings.map(f => `Tab trap in iframe (${f.frameUrl.slice(0, 60)})`).join('; ');
    const allDetail = [arrowDetail, iframeDetail].filter(Boolean).join('; ');
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Keyboard focus must not be trapped in a component',
        impact: 'serious',
        status: 'incomplete',
        reason: `Potential keyboard traps detected: ${allDetail}. Verify arrow key navigation and escape paths are available.`,
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Keyboard focus must not be trapped in a component',
      impact: 'critical',
      status: 'fail',
      reason: `Keyboard focus appears trapped in: ${trapHtml.slice(0, 120)}. Tab key could not escape the component even after pressing Escape.`,
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
