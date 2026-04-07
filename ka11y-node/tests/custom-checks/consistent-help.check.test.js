'use strict';

const { run, SC, RULE_ID, HELP_URL } = require('../../src/custom-checks/consistent-help.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

function makeData(overrides = {}) {
  return {
    helpLinks: [],
    chatWidget: false,
    hasChatbot: false,
    hasPhoneLink: false,
    hasEmailLink: false,
    ...overrides,
  };
}

describe('consistent-help.check (WCAG 3.2.6)', () => {
  // ── Module exports ─────────────────────────────────────────────────────────
  test('exports SC as 3.2.6', () => { expect(SC).toBe('3.2.6'); });
  test('exports RULE_ID as custom-consistent-help', () => { expect(RULE_ID).toBe('custom-consistent-help'); });
  test('exports HELP_URL', () => { expect(HELP_URL).toContain('consistent-help'); });

  // ── No help mechanism ─────────────────────────────────────────────────────
  test('returns incomplete when no help mechanisms are found', async () => {
    const page = makePage(makeData());
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.6');
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-consistent-help');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('No help');
    expect(result.rules[0].helpUrl).toBe(HELP_URL);
  });

  // ── Help links found ──────────────────────────────────────────────────────
  test('returns incomplete when help link is detected in footer', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'Contact Us', href: '/contact', inHeader: false, inFooter: true, inNav: false, html: '<a>Contact Us</a>' }],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('footer');
  });

  test('returns incomplete when help link is detected in header', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'Help', href: '/help', inHeader: true, inFooter: false, inNav: false, html: '<a>Help</a>' }],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('header');
  });

  test('returns incomplete when help link is detected in nav', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'Support', href: '/support', inHeader: false, inFooter: false, inNav: true, html: '<a>Support</a>' }],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('nav');
  });

  test('returns incomplete when help link is in body (not header/footer/nav)', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'FAQ', href: '/faq', inHeader: false, inFooter: false, inNav: false, html: '<a>FAQ</a>' }],
    }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('body');
  });

  test('location string includes multiple unique locations', async () => {
    const page = makePage(makeData({
      helpLinks: [
        { text: 'Help', href: '/help', inHeader: true, inFooter: false, inNav: false, html: '<a>Help</a>' },
        { text: 'Contact', href: '/contact', inHeader: false, inFooter: true, inNav: false, html: '<a>Contact</a>' },
      ],
    }));
    const result = await run(page);
    expect(result.rules[0].reason).toContain('header');
    expect(result.rules[0].reason).toContain('footer');
    expect(result.rules[0].reason).toContain('2 help link');
  });

  // ── Chat widget only ───────────────────────────────────────────────────────
  test('returns incomplete when only a chat widget is present', async () => {
    const page = makePage(makeData({ chatWidget: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('chat widget');
  });

  // ── Chatbot platform only ─────────────────────────────────────────────────
  test('returns incomplete when only chatbot platform is present', async () => {
    const page = makePage(makeData({ hasChatbot: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('chatbot platform');
  });

  // ── Phone link only ───────────────────────────────────────────────────────
  test('returns incomplete when only a phone link is present', async () => {
    const page = makePage(makeData({ hasPhoneLink: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('phone link');
  });

  // ── Email link only ───────────────────────────────────────────────────────
  test('returns incomplete when only an email link is present', async () => {
    const page = makePage(makeData({ hasEmailLink: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('email link');
  });

  // ── Combined extras ───────────────────────────────────────────────────────
  test('extras string includes all detected mechanisms', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'Help', href: '/help', inHeader: true, inFooter: false, inNav: false, html: '<a>Help</a>' }],
      chatWidget: true,
      hasChatbot: false,
      hasPhoneLink: true,
      hasEmailLink: true,
    }));
    const result = await run(page);
    expect(result.rules[0].reason).toContain('chat widget');
    expect(result.rules[0].reason).toContain('phone link');
    expect(result.rules[0].reason).toContain('email link');
  });

  test('reason when only chatbot and phone + no helpLinks', async () => {
    const page = makePage(makeData({ hasChatbot: true, hasPhoneLink: true }));
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('0 help link');
    expect(result.rules[0].reason).toContain('chatbot platform');
    expect(result.rules[0].reason).toContain('phone link');
  });

  // ── Impact & reason ────────────────────────────────────────────────────────
  test('impact is moderate when no help mechanisms found', async () => {
    const page = makePage(makeData());
    const result = await run(page);
    expect(result.rules[0].impact).toBe('moderate');
  });

  test('impact is null when help mechanisms are found', async () => {
    const page = makePage(makeData({ chatWidget: true }));
    const result = await run(page);
    expect(result.rules[0].impact).toBeNull();
  });

  test('reason includes single-page scan caveat', async () => {
    const page = makePage(makeData({
      helpLinks: [{ text: 'Help', href: '/help', inHeader: true, inFooter: false, inNav: false, html: '<a>Help</a>' }],
    }));
    const result = await run(page);
    expect(result.rules[0].reason).toContain('single-page scan');
  });

  // ── Source validation ─────────────────────────────────────────────────────
  test('includes Japanese help keywords in source heuristics', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/consistent-help.check.js'),
      'utf8'
    );
    expect(src).toContain('お問い合わせ');
    expect(src).toContain('ヘルプセンター');
    expect(src).toContain('チャット');
  });

  test('source includes known chatbot platform selectors', () => {
    const src = require('fs').readFileSync(
      require('path').resolve(__dirname, '../../src/custom-checks/consistent-help.check.js'),
      'utf8'
    );
    expect(src).toContain('intercom');
    expect(src).toContain('zendesk');
  });
});
