'use strict';

/**
 * Unit coverage for the checks added by the P1/P2 technique-coverage work.
 * Each test drives the check with a mocked Puppeteer page whose evaluate()
 * returns the in-page data shape the check expects, so the Node-side
 * classification/reporting logic is verified without a browser.
 */

const nonText = require('../../src/custom-checks/non-text-content.check');
const structure = require('../../src/custom-checks/structure-semantics.check');
const pageTitled = require('../../src/custom-checks/page-titled.check');
const formLabels = require('../../src/custom-checks/form-labels-instructions.check');
const submitControls = require('../../src/custom-checks/form-submit-controls.check');
const linkContext = require('../../src/custom-checks/link-purpose-in-context.check');
const bypass = require('../../src/custom-checks/bypass-blocks.check');
const nrv = require('../../src/custom-checks/name-role-value-states.check');
const langPage = require('../../src/custom-checks/language-of-page.check');
const resizeText = require('../../src/custom-checks/resize-text.check');
const keyboard = require('../../src/custom-checks/keyboard-operable.check');
const altTheme = require('../../src/custom-checks/contrast-alternate-theme.check');
const { runtimeHookScript, installRuntimeHooks } = require('../../src/custom-checks/runtimeHooks');

const once = (...values) => {
  const fn = jest.fn();
  for (const v of values) fn.mockResolvedValueOnce(v);
  fn.mockResolvedValue(undefined);
  return { evaluate: fn };
};

describe('metadata of the new checks', () => {
  test.each([
    [nonText, '1.1.1', 'custom-non-text-content', 'static'],
    [structure, '1.3.1', 'custom-structure-semantics', 'static'],
    [pageTitled, '2.4.2', 'custom-page-titled', 'static'],
    [formLabels, '3.3.2', 'custom-form-labels-instructions', 'static'],
    [submitControls, '3.2.2', 'custom-form-submit-controls', 'static'],
    [linkContext, '2.4.4', 'custom-link-purpose-in-context', 'static'],
    [bypass, '2.4.1', 'custom-bypass-blocks', 'static'],
    [nrv, '4.1.2', 'custom-name-role-value-states', 'static'],
    [langPage, '3.1.1', 'custom-language-of-page', 'static'],
    [resizeText, '1.4.4', 'custom-resize-text', 'interactive'],
    [keyboard, '2.1.1', 'custom-keyboard-operable', 'interactive'],
    [altTheme, '1.4.3', 'custom-contrast-alternate-theme', 'interactive'],
  ])('%#: exports SC/RULE_ID/MODE', (mod, sc, id, mode) => {
    expect(mod.SC).toBe(sc);
    expect(mod.RULE_ID).toBe(id);
    expect(mod.MODE).toBe(mode);
    expect(typeof mod.run).toBe('function');
  });
});

describe('non-text-content (1.1.1)', () => {
  test('passes with no issues', async () => {
    const r = await nonText.run(once({ issues: [], counts: { ariaLabelChecked: 3, images: 2, objects: 0 } }));
    expect(r.successCriteriaId).toBe('1.1.1');
    expect(r.rules[0].status).toBe('pass');
  });
  test('splits failures and review items', async () => {
    const r = await nonText.run(once({ issues: [
      { type: 'spacer-image-not-decorative', technique: 'C18', target: 'img', snippet: '<img>', detail: 'x' },
      { type: 'emoticon-no-alternative', technique: 'H86', target: 'p', snippet: '<p>', detail: 'y' },
    ], counts: {} }));
    expect(r.rules.map(x => x.status)).toEqual(['fail', 'incomplete']);
    expect(r.rules[0].reason).toContain('C18');
    expect(r.rules[1].ruleId).toBe('custom-non-text-content-review');
  });
  test('tolerates a non-object evaluate result', async () => {
    const r = await nonText.run(once([]));
    expect(r.rules[0].status).toBe('pass');
  });
});

describe('structure-semantics (1.3.1)', () => {
  test('fail + review rules', async () => {
    const r = await structure.run(once({ issues: [
      { type: 'heading-role-no-level', technique: 'ARIA12', severity: 'fail', target: 'div', snippet: '', detail: '' },
      { type: 'fake-heading', technique: 'G115', severity: 'review', target: 'div', snippet: '', detail: '' },
    ] }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].reason).toContain('ARIA12');
    expect(r.rules[1].status).toBe('incomplete');
  });
  test('passes when clean', async () => {
    const r = await structure.run(once({ issues: [] }));
    expect(r.rules[0].status).toBe('pass');
  });
});

describe('page-titled (2.4.2)', () => {
  test('generic title fails (G88)', async () => {
    const r = await pageTitled.run(once({ title: 'Home', h1s: ['Welcome'], host: 'example.com' }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].elements[0].technique).toBe('G88');
  });
  test('descriptive title with site name passes (G127)', async () => {
    const r = await pageTitled.run(once({ title: 'Pricing plans – Acme', h1s: ['Pricing plans'], host: 'acme.com', siteName: 'Acme' }));
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('site name');
  });
  test('title unrelated to heading needs review', async () => {
    const r = await pageTitled.run(once({ title: 'Bananas - Acme', h1s: ['Quarterly earnings report'], host: 'acme.com', siteName: 'Acme' }));
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].elements[0].type).toBe('title-unrelated-to-heading');
  });
  test('missing title defers to axe', async () => {
    const r = await pageTitled.run(once({ title: '', h1s: [] }));
    expect(r.rules[0].status).toBe('not_applicable');
  });
});

describe('form-labels-instructions (3.3.2)', () => {
  test('not applicable without fields', async () => {
    const r = await formLabels.run(once({ issues: [], counts: { inputs: 0 } }));
    expect(r.rules[0].status).toBe('not_applicable');
  });
  test('dangling describedby fails, others review', async () => {
    const r = await formLabels.run(once({ issues: [
      { type: 'describedby-dangling', technique: 'ARIA1', severity: 'fail', target: 'input', snippet: '', detail: '' },
      { type: 'required-no-visible-cue', technique: 'ARIA2', severity: 'review', target: 'input', snippet: '', detail: '' },
    ], counts: { inputs: 2 } }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[1].status).toBe('incomplete');
  });
});

describe('form-submit-controls (3.2.2)', () => {
  test('form without submit fails (H32)', async () => {
    const r = await submitControls.run(once({ forms: 1, autoControls: 0, issues: [{ type: 'form-no-submit', technique: 'H32', severity: 'fail', target: 'form', snippet: '', detail: '' }] }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].reason).toContain('H32');
  });
  test('passes when submit exists and auto controls are described', async () => {
    const r = await submitControls.run(once({ forms: 2, autoControls: 1, issues: [] }));
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('described in advance');
  });
});

describe('link-purpose-in-context (2.4.4)', () => {
  test('context-resolved generic links pass', async () => {
    const r = await linkContext.run(once({ checked: 10, generic: 2, resolvedByContext: 2, issues: [] }));
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('2 generic');
  });
  test('unresolved generic link fails', async () => {
    const r = await linkContext.run(once({ checked: 3, generic: 1, resolvedByContext: 0, issues: [{ type: 'generic-link-no-context', target: 'a', snippet: '', text: 'click here', detail: '' }] }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].reason).toContain('"click here"');
  });
});

describe('bypass-blocks (2.4.1)', () => {
  test('skip link passes', async () => {
    const r = await bypass.run(once({ mechanisms: ['skip link (G1)', 'main landmark'], issues: [], navLinksBeforeMain: 40 }));
    expect(r.rules[0].status).toBe('pass');
  });
  test('long nav without skip mechanism is advisory', async () => {
    const r = await bypass.run(once({ mechanisms: ['main landmark', '4 heading(s)'], issues: [], navLinksBeforeMain: 30 }));
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].reason).toContain('30 navigation links');
  });
  test('broken skip target fails', async () => {
    const r = await bypass.run(once({ mechanisms: [], issues: [{ type: 'skip-link-broken-target', technique: 'G1', target: 'a', snippet: '', detail: 'broken' }], navLinksBeforeMain: 2 }));
    expect(r.rules[0].status).toBe('fail');
  });
});

describe('name-role-value-states (4.1.2)', () => {
  test('missing aria-expanded fails (G108)', async () => {
    const r = await nrv.run(once({ controls: 3, issues: [{ type: 'missing-aria-expanded', technique: 'G108', severity: 'fail', target: 'button', snippet: '', detail: '' }] }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].reason).toContain('G108');
  });
  test('obsolete element is review (H88)', async () => {
    const r = await nrv.run(once({ controls: 0, issues: [{ type: 'obsolete-element', technique: 'H88', severity: 'review', target: 'font', snippet: '', detail: '' }] }));
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].ruleId).toBe('custom-name-role-value-states-review');
  });
});

describe('language-of-page (3.1.1, SVR5)', () => {
  const doc = { lang: 'en', xml: '', metaLang: '', total: 1000, cjk: 0, kana: 0, hangul: 0, cyr: 0, arabic: 0, latin: 900 };
  test('header agreeing with lang passes', async () => {
    const page = once(doc); page.__ka11yNav = { headers: { 'content-language': 'en-GB' }, redirectChain: [] };
    const r = await langPage.run(page);
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('en-GB');
  });
  test('header disagreeing with lang is advisory', async () => {
    const page = once(doc); page.__ka11yNav = { headers: { 'content-language': 'ja' }, redirectChain: [] };
    const r = await langPage.run(page);
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].elements[0].technique).toBe('SVR5');
  });
  test('japanese text declared as english fails', async () => {
    const r = await langPage.run(once({ ...doc, kana: 400, cjk: 800, latin: 50 }));
    expect(r.rules[0].status).toBe('fail');
  });
});

describe('resize-text (1.4.4)', () => {
  test('clipping at 200% fails (C28)', async () => {
    const r = await resizeText.run(once({ px: 10, relative: 2, textSizeControls: 0, touchBlockers: 0, textElements: 40 },
      { applied: 40, clipped: [{ target: 'div', snippet: '', detail: 'cut' }], cutControls: [], overlaps: [], skipped: false }));
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules.find(x => x.ruleId === 'custom-resize-text-units').status).toBe('incomplete');
  });
  test('text-size control downgrades to review (G178)', async () => {
    const r = await resizeText.run(once({ px: 1, relative: 9, textSizeControls: 1, touchBlockers: 1, textElements: 40 },
      { applied: 40, clipped: [{ target: 'div', snippet: '', detail: 'cut' }], cutControls: [], overlaps: [], skipped: false }));
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules.find(x => x.ruleId === 'custom-resize-text-touch-zoom')).toBeTruthy();
  });
  test('clean page passes', async () => {
    const r = await resizeText.run(once({ px: 0, relative: 0, textSizeControls: 0, touchBlockers: 0, textElements: 10 },
      { applied: 10, clipped: [], cutControls: [], overlaps: [], skipped: false }));
    expect(r.rules[0].status).toBe('pass');
  });
});

describe('keyboard-operable (2.1.1)', () => {
  test('mouse-only handler fails without simulation (no keyboard on mock)', async () => {
    const page = once({ registryAvailable: true, checked: 2, mouseOnly: [{ target: 'div', snippet: '', types: 'click', detail: 'x' }], hoverOnly: [], candidates: [], sliders: [] });
    const r = await keyboard.run(page);
    expect(r.rules[0].status).toBe('fail');
    expect(r.rules[0].elements[0].technique).toBe('G90');
  });
  test('passes when nothing suspicious', async () => {
    const r = await keyboard.run(once({ registryAvailable: true, checked: 0, mouseOnly: [], hoverOnly: [], candidates: [], sliders: [] }));
    expect(r.rules[0].status).toBe('pass');
  });
});

describe('contrast-alternate-theme (1.4.3)', () => {
  test('no toggle and no media queries → not applicable', async () => {
    const r = await altTheme.run(once({ toggles: [], pickers: 0, mediaQueries: [] }));
    expect(r.rules[0].status).toBe('not_applicable');
  });
  test('prefers-contrast styles credited (G174)', async () => {
    const r = await altTheme.run(once({ toggles: [], pickers: 0, mediaQueries: ['(prefers-contrast: more)'] }));
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('prefers-contrast');
  });
});

describe('runtime hooks', () => {
  test('installRuntimeHooks returns false for pages without evaluateOnNewDocument', async () => {
    expect(await installRuntimeHooks({})).toBe(false);
  });
  test('hook script registers listener registry, canvas and audio hooks in a jsdom-like window', () => {
    const src = String(runtimeHookScript);
    for (const key of ['listenersOf', 'docListeners', 'canvasTextOf', 'audioContexts', 'mediaPlay', 'windowOpen']) expect(src).toContain(key);
  });
});

describe('phase 3 helpers', () => {
  test('captureFlashProfile returns null without a CDP session (mock page)', async () => {
    const { captureFlashProfile, GENERAL_AREA_THRESHOLD } = require('../../src/custom-checks/flashAnalysis');
    expect(await captureFlashProfile({ evaluate: jest.fn() })).toBeNull();
    expect(GENERAL_AREA_THRESHOLD).toBeGreaterThan(0);
  });
  test('three-flashes still runs on a mock page (screencast skipped)', async () => {
    const tf = require('../../src/custom-checks/three-flashes.check');
    const r = await tf.run({ evaluate: jest.fn().mockResolvedValue({ issues: [] }) });
    expect(r.rules[0].status).toBe('pass');
  });
  test('headings relevance rule is advisory only (G130)', async () => {
    const h = require('../../src/custom-checks/headings-and-labels.check');
    const r = await h.run({ evaluate: jest.fn().mockResolvedValue({ violations: [{ type: 'heading-unrelated', target: 'h2', snippet: '', detail: 'x' }], headingCount: 3, labelCount: 0 }) });
    expect(r.rules[0].ruleId).toBe('custom-headings-and-labels-relevance');
    expect(r.rules[0].status).toBe('incomplete');
  });
  test('unusual-words passes when all rare words are defined in place (G112)', async () => {
    const u = require('../../src/custom-checks/unusual-words.check');
    const r = await u.run({ evaluate: jest.fn().mockResolvedValue({ hasDefinitionMechanism: false, hasComplexContent: true, jargonCount: 12, rareUndefined: [], rareDefined: 4, rareTotal: 4 }) });
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].reason).toContain('G112');
  });
  test('link-purpose credits a descriptive-link-text switch (G189)', async () => {
    const lp = require('../../src/custom-checks/link-purpose.check');
    const r = await lp.run({ evaluate: jest.fn().mockResolvedValue({ violations: [{ text: 'more', html: '<a>', element_id: null, target: ['a'], tag: 'A' }], checkedCount: 3, hasLinkTextSwitch: true }) });
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].reason).toContain('G189');
  });
});
