'use strict';

const AccessibilityController = require('../../src/controllers/accessibility.controller');

function makeRes() {
  return {
    status: jest.fn().mockReturnThis(),
    json: jest.fn(),
  };
}

describe('AccessibilityController.analyseUrlFlat', () => {
  let service;
  let logger;
  let controller;

  beforeEach(() => {
    service = {
      analyseUrlFlat: jest.fn(),
    };
    logger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn(),
    };
    controller = new AccessibilityController(service, logger);
  });

  test('forwards successCriteriaId and crawl options to the service', async () => {
    const req = {
      body: {
        url: 'https://example.com',
        level: 'AA',
        lang: 'en',
        successCriteriaId: '1.1.1',
      },
    };
    const res = makeRes();
    const findings = [{ rule_id: 'image-alt', wcag_sc: '1.1.1' }];
    service.analyseUrlFlat.mockResolvedValue(findings);

    await controller.analyseUrlFlat(req, res);

    // successCriteriaId is now delivered inside the crawl-options object
    // (alongside maxDepth/internalLinks/maxPages), not as a bare 4th arg.
    // timings is undefined when no jobId is supplied; discoveredUrls defaults
    // to an empty array (R-1) and is forwarded so the service can choose
    // snapshot-fed vs legacy BFS mode.
    expect(service.analyseUrlFlat).toHaveBeenCalledWith(
      'https://example.com',
      'AA',
      'en',
      expect.objectContaining({
        maxDepth: 0,
        internalLinks: true,
        maxPages: 50,
        successCriteriaId: '1.1.1',
        discoveredUrls: [],
      }),
    );
    expect(res.json).toHaveBeenCalledWith({ url: 'https://example.com', findings, scannedPages: [] });
  });

  test('forwards maxDepth / internalLinks / maxPages (clamped) to the service', async () => {
    const req = {
      body: {
        url: 'https://example.com',
        maxDepth: 99,          // clamped to 5
        internalLinks: false,
        maxPages: 9999,        // clamped to 200
      },
    };
    const res = makeRes();
    service.analyseUrlFlat.mockResolvedValue([]);

    await controller.analyseUrlFlat(req, res);

    expect(service.analyseUrlFlat).toHaveBeenCalledWith(
      'https://example.com',
      'AA',
      'en',
      expect.objectContaining({
        maxDepth: 5,
        internalLinks: false,
        maxPages: 200,
        successCriteriaId: null,
        discoveredUrls: [],
      }),
    );
  });

  test('R-1: clamps + forwards discoveredUrls to the service when provided', async () => {
    const req = {
      body: {
        url: 'https://example.com',
        maxPages: 5,
        discoveredUrls: [
          'https://example.com/a',
          'https://example.com/b',
          'https://example.com/c',
          'https://example.com/d',
          'https://example.com/e',
          'https://example.com/f', // beyond maxPages — should be dropped
          12345,                   // wrong type — should be dropped
          '',                      // empty — should be dropped
          'x'.repeat(3000),        // too long — should be dropped
        ],
      },
    };
    const res = makeRes();
    service.analyseUrlFlat.mockResolvedValue([]);

    await controller.analyseUrlFlat(req, res);

    const callArgs = service.analyseUrlFlat.mock.calls[0][3];
    expect(callArgs.discoveredUrls).toEqual([
      'https://example.com/a',
      'https://example.com/b',
      'https://example.com/c',
      'https://example.com/d',
      'https://example.com/e',
    ]);
  });

  test('rejects invalid successCriteriaId format before calling the service', async () => {
    const req = {
      body: {
        url: 'https://example.com',
        successCriteriaId: 'bad-id',
      },
    };
    const res = makeRes();

    await controller.analyseUrlFlat(req, res);

    expect(service.analyseUrlFlat).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(400);
    expect(res.json).toHaveBeenCalledWith({
      error: 'successCriteriaId must match format X.Y.Z (e.g. "1.1.1")',
    });
  });
});
