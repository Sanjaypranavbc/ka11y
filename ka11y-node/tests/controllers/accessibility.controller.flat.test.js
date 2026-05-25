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
    expect(service.analyseUrlFlat).toHaveBeenCalledWith(
      'https://example.com',
      'AA',
      'en',
      { maxDepth: 0, internalLinks: true, maxPages: 50, successCriteriaId: '1.1.1' },
    );
    expect(res.json).toHaveBeenCalledWith({ url: 'https://example.com', findings });
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
      { maxDepth: 5, internalLinks: false, maxPages: 200, successCriteriaId: null },
    );
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
