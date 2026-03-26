'use strict';

const { run } = require('../../src/custom-checks/images-of-text.check');

function makePage(result) {
  return { evaluate: jest.fn().mockResolvedValue(result) };
}

const emptyData = { violations: [], needsReview: [], bgTextViolations: [], checkedCount: 0 };

describe('images-of-text.check (WCAG 1.4.5)', () => {
  test('passes when no text-image candidates found', async () => {
    const page = makePage({ ...emptyData, checkedCount: 5 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('1.4.5');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-images-of-text');
  });

  test('fails when high-confidence text-image violations detected', async () => {
    const page = makePage({
      ...emptyData,
      checkedCount: 10,
      violations: [
        { src: '/banners/headline.png', alt: 'Get 50% off today', html: '<img src="...">', id: null },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('1 image(s)');
  });

  test('returns incomplete for needs_review items only', async () => {
    const page = makePage({
      ...emptyData,
      checkedCount: 8,
      needsReview: [
        { src: '/img/promo.png', alt: 'Limited time offer ends soon', html: '<img src="...">', id: null },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('1 image(s)');
  });

  test('bg violations count as failures', async () => {
    const page = makePage({
      ...emptyData,
      bgTextViolations: [
        { src: 'url(/banners/promo.jpg)', text: 'Sale ends tonight', html: '<div>', id: null },
      ],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });

  test('passes with descriptive message when no images found', async () => {
    const page = makePage(emptyData);
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No candidate images');
  });

  test('fail takes precedence over needs_review', async () => {
    const page = makePage({
      ...emptyData,
      violations:   [{ src: '/banner.png', alt: 'Buy now save big money today', html: '', id: null }],
      needsReview:  [{ src: '/promo.png',  alt: 'Save more today on all items', html: '', id: null }],
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
  });
});
