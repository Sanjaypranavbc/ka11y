'use strict';

const { run } = require('../../src/custom-checks/consistent-help.check');
const { getKeywordList } = require('../../src/custom-checks/sharedAssets');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('consistent-help.check (WCAG 3.2.6)', () => {
  test('returns incomplete when no help mechanisms are found', async () => {
    const page = makePage({ helpLinks: [], chatWidget: false });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.2.6');
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].ruleId).toBe('custom-consistent-help');
  });

  test('passes when help link is detected in footer', async () => {
    const page = makePage({
      helpLinks: [{ text: 'Contact Us', href: '/contact', inHeader: false, inFooter: true, inNav: false, html: '<a href="/contact">Contact Us</a>' }],
      chatWidget: false,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('footer');
  });

  test('passes when only a chat widget is present', async () => {
    const page = makePage({ helpLinks: [], chatWidget: true });
    const result = await run(page);
    // A chat widget is a valid help mechanism — should pass
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('chat widget');
  });

  test('pass reason includes location info', async () => {
    const page = makePage({
      helpLinks: [
        { text: 'Help', href: '/help', inHeader: true, inFooter: false, inNav: false, html: '<a href="/help">Help</a>' },
      ],
      chatWidget: false,
    });
    const result = await run(page);
    expect(result.rules[0].reason).toContain('header');
  });

  test('loads Japanese help keywords from shared universal config', () => {
    const helpKeywords = getKeywordList('consistent_help', 'help_keywords');
    const chatKeywords = getKeywordList('consistent_help', 'chat_keywords');
    expect(helpKeywords).toContain('お問い合わせ');
    expect(helpKeywords).toContain('ヘルプセンター');
    expect(chatKeywords).toContain('チャット');
  });
});
