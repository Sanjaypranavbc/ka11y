'use strict';

jest.mock('dns', () => ({
  promises: {
    lookup: jest.fn().mockResolvedValue([{ address: '93.184.216.34', family: 4 }]),
  },
}));

jest.mock('../../src/utils/axeResultMapper', () => {
  const actual = jest.requireActual('../../src/utils/axeResultMapper');
  return {
    ...actual,
    mapResults: jest.fn().mockReturnValue([{ successCriteriaId: '1.1.1', rules: [{ ruleId: 'image-alt' }] }]),
    mapResultsFlat: jest.fn().mockReturnValue([]),
    mapCustomResultsFlat: jest.fn().mockReturnValue([]),
  };
});

jest.mock('../../src/custom-checks/index', () => ({
  runAll: jest.fn(),
  runStaticChecks: jest.fn(),
  mergeWithAxe: jest.fn((axe, custom) => [...axe, ...custom]),
}));

const { runAll, runStaticChecks, mergeWithAxe } = require('../../src/custom-checks/index');
const AccessibilityService = require('../../src/services/accessibility.service');

function makePage(axeResults) {
  return {
    setDefaultTimeout: jest.fn(),
    setDefaultNavigationTimeout: jest.fn(),
    setBypassCSP: jest.fn().mockResolvedValue(undefined),
    setRequestInterception: jest.fn().mockResolvedValue(undefined),
    setContent: jest.fn().mockResolvedValue(undefined),
    goto: jest.fn().mockResolvedValue(undefined),
    addScriptTag: jest.fn().mockResolvedValue(undefined),
    waitForFunction: jest.fn().mockResolvedValue(undefined),
    on: jest.fn(),
    evaluate: jest.fn().mockResolvedValue(axeResults),
  };
}

function makeService(page) {
  const browser = {
    newPage: jest.fn().mockResolvedValue(page),
    close: jest.fn().mockResolvedValue(undefined),
  };

  const puppeteer = {
    launch: jest.fn().mockResolvedValue(browser),
  };

  const logger = {
    info: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
    error: jest.fn(),
  };

  const config = {
    browser: {
      headless: 'shell',
      executablePath: undefined,
      args: [],
    },
    axe: {
      timeoutMs: 10_000,
      runOnly: { type: 'tag', values: ['wcag2a'] },
    },
  };

  return new AccessibilityService(puppeteer, '/fake/axe.min.js', logger, config);
}

describe('AccessibilityService criterion-aware custom-check execution', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('analyze passes successCriteriaId to static custom checks', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    const service = makeService(page);

    runStaticChecks.mockResolvedValue([
      {
        successCriteriaId: '1.1.1',
        rules: [{ ruleId: 'custom-html-parsing', status: 'pass' }],
      },
    ]);

    const results = await service.analyze('<main>Hello</main>', '1.1.1');

    expect(runStaticChecks).toHaveBeenCalledWith(page, '1.1.1');
    expect(page.evaluate).toHaveBeenCalledWith(
      expect.any(Function),
      expect.objectContaining({
        type: 'rule',
        values: expect.arrayContaining(['image-alt']),
      }),
    );
    expect(mergeWithAxe).toHaveBeenCalledTimes(1);
    expect(results).toEqual(expect.arrayContaining([
      expect.objectContaining({ successCriteriaId: '1.1.1' }),
    ]));
  });

  test('analyseUrl passes successCriteriaId to full custom check pipeline', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    const service = makeService(page);

    runAll.mockResolvedValue([
      {
        successCriteriaId: '1.1.1',
        rules: [{ ruleId: 'custom-html-parsing', status: 'pass' }],
      },
    ]);

    const results = await service.analyseUrl('https://example.com', '1.1.1');

    expect(runAll).toHaveBeenCalledWith(page, '1.1.1');
    expect(page.evaluate).toHaveBeenCalledWith(
      expect.any(Function),
      expect.objectContaining({
        type: 'rule',
        values: expect.arrayContaining(['image-alt']),
      }),
    );
    expect(mergeWithAxe).toHaveBeenCalledTimes(1);
    expect(results).toEqual(expect.arrayContaining([
      expect.objectContaining({ successCriteriaId: '1.1.1' }),
    ]));
  });
});
