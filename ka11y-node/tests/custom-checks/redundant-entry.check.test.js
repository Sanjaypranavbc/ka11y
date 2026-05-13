'use strict';

const { run, __test__ } = require('../../src/custom-checks/redundant-entry.check');

function makePage(data, frameDataList = []) {
  const mainFrame = { _mockMain: true };
  const extraFrames = frameDataList.map((frameData, index) => ({
    _mockFrame: index + 1,
    evaluate: jest.fn().mockResolvedValue(frameData),
  }));

  return {
    evaluate: jest.fn().mockResolvedValue(data),
    waitForLoadState: jest.fn().mockResolvedValue(undefined),
    waitForNetworkIdle: jest.fn().mockResolvedValue(undefined),
    waitForSelector: jest.fn().mockResolvedValue(undefined),
    mainFrame: jest.fn(() => mainFrame),
    frames: jest.fn(() => [mainFrame, ...extraFrames]),
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
      target: ['input[name="email"]'],
      tag: 'INPUT',
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
        target: ['input[name="zip"]'],
        tag: 'INPUT',
        html: '<input name="zip">',
      }),
      expect.objectContaining({
        target: ['input[name="postal_code"]'],
        tag: 'INPUT',
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

  test('treats contact and subscribe forms as different processes', () => {
    expect(__test__.inferProcessTypeFromTexts(
      'contact form submit contact us',
      'email address full name phone'
    )).toBe('contact');

    expect(__test__.inferProcessTypeFromTexts(
      'subscribe form get the fresh news subscribe',
      'your email here'
    )).toBe('subscribe');

    expect(__test__.areLikelySameProcessAcrossForms([
      {
        formRef: 'form:contact',
        formProcessType: 'contact',
        processType: 'contact',
        purposeSignature: 'email|contact',
      },
      {
        formRef: 'form:subscribe',
        formProcessType: 'subscribe',
        processType: 'subscribe',
        purposeSignature: 'email|subscribe',
      },
    ], {
      samePurposePairs: 0,
      distinctPurposePairs: 0,
    })).toBe(false);
  });

  test('still treats checkout forms as the same process across forms', () => {
    expect(__test__.areLikelySameProcessAcrossForms([
      {
        formRef: 'form:shipping',
        formProcessType: 'checkout',
        processType: 'checkout',
        purposeSignature: 'email|checkout|shipping',
      },
      {
        formRef: 'form:billing',
        formProcessType: 'checkout',
        processType: 'checkout',
        purposeSignature: 'email|checkout|billing',
      },
    ], {
      samePurposePairs: 1,
      distinctPurposePairs: 0,
    })).toBe(true);
  });

  test('merges legacy frame groups without strongSamePurpose and still classifies correctly', async () => {
    const mainData = {
      formCount: 1,
      candidateCount: 4,
      globalReuseControlCount: 0,
      repeatedGroups: [{
        key: 'email',
        fieldCount: 2,
        requiredCount: 2,
        uniqueForms: 1,
        hasPrefilledRepeat: false,
        hasAutocompleteSupport: false,
        hasReuseMechanism: false,
        highConfidence: false,
        needsReview: true,
        samePurpose: true,
        clearlyDifferentPurpose: false,
        samePurposePairs: 1,
        distinctPurposePairs: 0,
        purposeSignatures: ['email|contact'],
        processTypes: ['contact'],
        sampleSelectors: ['input[name="email"]'],
        allSelectors: ['input[name="email"]'],
      }],
      highConfidenceGroups: [],
      reviewGroups: [{
        key: 'email',
        requiredCount: 2,
        sampleSelectors: ['input[name="email"]'],
      }],
    };

    const frameData = {
      formCount: 1,
      candidateCount: 4,
      globalReuseControlCount: 0,
      repeatedGroups: [{
        key: 'email',
        fieldCount: 2,
        requiredCount: 2,
        uniqueForms: 1,
        hasPrefilledRepeat: false,
        hasAutocompleteSupport: false,
        hasReuseMechanism: false,
        highConfidence: true,
        needsReview: false,
        samePurpose: true,
        strongSamePurpose: true,
        clearlyDifferentPurpose: false,
        samePurposePairs: 2,
        distinctPurposePairs: 0,
        purposeSignatures: ['email|contact'],
        processTypes: ['contact'],
        sampleSelectors: ['input[name="contact_email"]'],
        allSelectors: ['input[name="contact_email"]'],
      }],
      highConfidenceGroups: [{
        key: 'email',
        requiredCount: 2,
        sampleSelectors: ['input[name="contact_email"]'],
      }],
      reviewGroups: [],
    };

    const page = makePage(mainData, [frameData]);
    const result = await run(page);

    expect(result.rules[0].status).toBe('fail');
    expect(result.rules[0].elements).toEqual(expect.arrayContaining([
      expect.objectContaining({
        target: ['input[name="email"]'],
        tag: 'INPUT',
      }),
      expect.objectContaining({
        target: ['input[name="contact_email"]'],
        tag: 'INPUT',
      }),
    ]));

  });

  // Regression: page.evaluate(evaluatePage) was throwing
  // `ReferenceError: areLikelySameProcessAcrossForms is not defined`
  // whenever the audit reached the grouping branch — the module-level
  // function with that name does not survive serialisation into the
  // browser context. A local copy now lives inside evaluatePage. This
  // test asserts the local definition is present so the bug cannot
  // silently regress, since the rest of the suite mocks page.evaluate
  // and never exercises the real browser-side body.
  test('evaluatePage defines areLikelySameProcessAcrossForms locally', () => {
    const fs = require('fs');
    const path = require('path');
    const src = fs.readFileSync(
      path.resolve(
        __dirname,
        '../../src/custom-checks/redundant-entry.check.js'
      ),
      'utf8'
    );

    const startMatch = src.match(/function evaluatePage\([^)]*\)\s*\{/);
    expect(startMatch).toBeTruthy();
    const startIdx = startMatch.index + startMatch[0].length;
    // The first occurrence of "\n}\n\nfunction " at column 0 after the
    // body's start closes evaluatePage.
    const endRel = src.slice(startIdx).search(/\n\}\s*\n\s*function\s/);
    expect(endRel).toBeGreaterThan(0);
    const body = src.slice(startIdx, startIdx + endRel);

    if (/\bareLikelySameProcessAcrossForms\s*\(/.test(body)) {
      expect(body).toMatch(/function\s+areLikelySameProcessAcrossForms\s*\(/);
    }
  });
});
