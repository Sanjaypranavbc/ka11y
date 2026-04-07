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

  test('forwards successCriteriaId to the service', async () => {
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

    expect(service.analyseUrlFlat).toHaveBeenCalledWith(
      'https://example.com',
      'AA',
      'en',
      '1.1.1',
    );
    expect(res.json).toHaveBeenCalledWith({ url: 'https://example.com', findings });
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
