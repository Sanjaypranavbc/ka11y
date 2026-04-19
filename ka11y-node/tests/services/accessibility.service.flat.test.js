'use strict';

jest.mock('dns', () => ({
  promises: {
    lookup: jest.fn().mockResolvedValue([{ address: '93.184.216.34', family: 4 }]),
  },
}));

jest.mock('../../src/custom-checks/index', () => ({
  runAll: jest.fn(),
  runStaticChecks: jest.fn(),
  mergeWithAxe: jest.fn(),
}));

const { runAll } = require('../../src/custom-checks/index');
const AccessibilityService = require('../../src/services/accessibility.service');

function makePage(axeResults) {
  return {
    setDefaultTimeout: jest.fn(),
    setDefaultNavigationTimeout: jest.fn(),
    setBypassCSP: jest.fn().mockResolvedValue(undefined),
    setRequestInterception: jest.fn().mockResolvedValue(undefined),
    on: jest.fn(),
    goto: jest.fn().mockResolvedValue(undefined),
    addScriptTag: jest.fn().mockResolvedValue(undefined),
    waitForFunction: jest.fn().mockResolvedValue(undefined),
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
      ignoreHTTPSErrors: true,
      args: [],
    },
    axe: {
      timeoutMs: 10_000,
      runOnly: { type: 'tag', values: ['wcag2a'] },
    },
  };

  return new AccessibilityService(puppeteer, '/fake/axe.min.js', logger, config);
}

describe('AccessibilityService.analyseUrlFlat', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('includes custom-check findings in flat results for matching WCAG level', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    const service = makeService(page);

    runAll.mockResolvedValue([
      {
        successCriteriaId: '3.3.8', // AA
        rules: [{
          ruleId: 'custom-accessible-auth',
          impact: 'serious',
          status: 'fail',
          reason: 'Authentication challenge has no accessible alternative.',
          helpUrl: 'https://example.com/sc-338',
        }],
      },
    ]);

    const findings = await service.analyseUrlFlat('https://example.com', 'AA');

    expect(runAll).toHaveBeenCalledTimes(1);
    expect(findings).toHaveLength(1);
    expect(findings[0].rule_id).toBe('custom-accessible-auth');
    expect(findings[0].status).toBe('fail');
    expect(findings[0].source).toBe('custom');
  });

  test('filters out higher-level custom findings when running level A', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    const service = makeService(page);

    runAll.mockResolvedValue([
      {
        successCriteriaId: '3.3.8', // AA
        rules: [{
          ruleId: 'custom-accessible-auth',
          impact: 'serious',
          status: 'fail',
          reason: 'Authentication challenge has no accessible alternative.',
          helpUrl: 'https://example.com/sc-338',
        }],
      },
    ]);

    const findings = await service.analyseUrlFlat('https://example.com', 'A');

    expect(runAll).toHaveBeenCalledTimes(1);
    expect(findings).toEqual([]);
  });

  test('bypasses CSP and retries axe injection when axe is initially unavailable', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    page.waitForFunction
      .mockRejectedValueOnce(new Error('axe is not defined'))
      .mockResolvedValueOnce(undefined);

    const service = makeService(page);
    runAll.mockResolvedValue([]);

    const findings = await service.analyseUrlFlat('https://example.com', 'AA');

    expect(page.setBypassCSP).toHaveBeenCalledWith(true);
    expect(service._puppeteer.launch).toHaveBeenCalledWith(expect.objectContaining({
      ignoreHTTPSErrors: true,
    }));
    expect(page.addScriptTag).toHaveBeenCalledTimes(2);
    expect(page.waitForFunction).toHaveBeenCalledTimes(2);
    expect(findings).toEqual([]);
  });

  test('configures axe-core locale when lang=ja', async () => {
    const page = makePage({ violations: [], passes: [], incomplete: [] });
    const service = makeService(page);
    runAll.mockResolvedValue([]);

    await service.analyseUrlFlat('https://example.com', 'AA', 'ja');

    const localeCall = page.evaluate.mock.calls.find(([fn]) =>
      typeof fn === 'function' && fn.toString().includes('axe.configure')
    );
    expect(localeCall).toBeTruthy();
    expect(localeCall[1]).toMatchObject({
      rules: expect.any(Object),
      checks: expect.any(Object),
    });
  });
});
