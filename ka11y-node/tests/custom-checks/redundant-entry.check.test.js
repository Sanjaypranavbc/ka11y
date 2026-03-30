'use strict';

const { run } = require('../../src/custom-checks/redundant-entry.check');

function makePage(data) {
  return {
    evaluate: jest.fn().mockResolvedValue(data),
    waitForLoadState: jest.fn().mockResolvedValue(undefined),
    waitForNetworkIdle: jest.fn().mockResolvedValue(undefined),
    waitForSelector: jest.fn().mockResolvedValue(undefined),
    mainFrame: jest.fn(() => ({ _mockMain: true })),
    frames: jest.fn(() => []),
  };
}

describe('redundant-entry.check (WCAG 3.3.7)', () => {
  test('passes when no forms are found', async () => {
    const page = makePage({
      formCount: 0,
      candidateCount: 0,
      repeatedGroups: [],
      highConfidenceGroups: [],
      reviewGroups: [],
      reuseControlCount: 0,
    });

    const result = await run(page);
    expect(result.successCriteriaId).toBe('3.3.7');
    expect(result.rules[0].ruleId).toBe('custom-redundant-entry');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('No forms');
  });

  test('passes when no repeated required personal-data groups are detected', async () => {
    const page = makePage({
      formCount: 2,
      candidateCount: 6,
      repeatedGroups: [],
      highConfidenceGroups: [],
      reviewGroups: [],
      reuseControlCount: 0,
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('no repeated required personal-data fields');
  });

  test('fails when high-confidence redundant-entry issues are detected', async () => {
    const page = makePage({
      formCount: 2,
      candidateCount: 8,
      repeatedGroups: [{
        key: 'email',
        fieldCount: 2,
        requiredCount: 2,
        highConfidence: true,
        needsReview: false,
        sampleSelectors: ['input[name="email"]', 'input[name="contact_email"]'],
      }],
      highConfidenceGroups: [{
        key: 'email',
        requiredCount: 2,
        sampleSelectors: ['input[name="email"]', 'input[name="contact_email"]'],
      }],
      reviewGroups: [],
      reuseControlCount: 0,
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('high-confidence redundant-entry issue');
    expect(Array.isArray(result.rules[0].elements)).toBe(true);
    expect(result.rules[0].elements[0]).toMatchObject({
      selector: 'input[name="email"]',
      tagName: 'INPUT',
      html: '<input name="email">',
    });
  });

  test('returns incomplete when repeated required fields need manual verification', async () => {
    const page = makePage({
      formCount: 2,
      candidateCount: 7,
      repeatedGroups: [{
        key: 'postal-code',
        fieldCount: 2,
        requiredCount: 2,
        highConfidence: false,
        needsReview: true,
        sampleSelectors: ['input[name="zip"]', 'input[name="postal_code"]'],
      }],
      highConfidenceGroups: [],
      reviewGroups: [{
        key: 'postal-code',
        requiredCount: 2,
        sampleSelectors: ['input[name="zip"]', 'input[name="postal_code"]'],
      }],
      reuseControlCount: 0,
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('moderate');
    expect(result.rules[0].reason).toContain('manual verification');
    expect(Array.isArray(result.rules[0].elements)).toBe(true);
    expect(result.rules[0].elements).toEqual(expect.arrayContaining([
      expect.objectContaining({
        selector: 'input[name="zip"]',
        tagName: 'INPUT',
        html: '<input name="zip">',
      }),
      expect.objectContaining({
        selector: 'input[name="postal_code"]',
        tagName: 'INPUT',
        html: '<input name="postal_code">',
      }),
    ]));
  });

  test('passes when repeated fields have reuse or prefill mechanisms', async () => {
    const page = makePage({
      formCount: 2,
      candidateCount: 8,
      repeatedGroups: [{
        key: 'address-line1',
        fieldCount: 2,
        requiredCount: 2,
        highConfidence: false,
        needsReview: false,
        hasReuseMechanism: true,
        sampleSelectors: ['input[name="shipping_address"]', 'input[name="billing_address"]'],
      }],
      highConfidenceGroups: [],
      reviewGroups: [],
      reuseControlCount: 1,
    });

    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].reason).toContain('reuse or prefill mechanisms');
  });
});
