'use strict';

const request = require('supertest');
const express = require('express');
const AccessibilityController = require('../src/controllers/accessibility.controller');
const { SsrfGuardError } = require('../src/services/accessibility.service');

describe('AccessibilityController', () => {
  let app;
  let mockService;
  let mockLogger;

  beforeEach(() => {
    mockService = {
      analyze: jest.fn(),
      analyseUrlFlat: jest.fn(),
      analyseUrl: jest.fn(),
    };
    mockLogger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn(),
    };
    const controller = new AccessibilityController(mockService, mockLogger);
    app = express();
    app.use(express.json());
    app.post('/analyze', (req, res) => controller.analyze(req, res));
    app.post('/analyse-url-flat', (req, res) => controller.analyseUrlFlat(req, res));
    app.post('/analyse-url', (req, res) => controller.analyseUrl(req, res));
    app.post('/rules/:successCriteriaId/analyse-url', (req, res) => controller.analyseRuleUrl(req, res));
  });

  describe('POST /analyze', () => {
    it('returns 400 if html is missing', async () => {
      const res = await request(app).post('/analyze').send({});
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('html field is required');
    });

    it('returns 400 if successCriteriaId is malformed', async () => {
      const res = await request(app).post('/analyze').send({ html: '...', successCriteriaId: 'invalid' });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('successCriteriaId must match format');
    });

    it('returns 200 and results on success', async () => {
      mockService.analyze.mockResolvedValue([{ sc: '1.1.1', rules: [] }]);
      const res = await request(app).post('/analyze').send({ html: '<html></html>' });
      expect(res.status).toBe(200);
      expect(res.body.results).toHaveLength(1);
    });

    it('returns 500 on service error', async () => {
      mockService.analyze.mockRejectedValue(new Error('Internal oops'));
      const res = await request(app).post('/analyze').send({ html: '<html></html>' });
      expect(res.status).toBe(500);
      expect(res.body.error).toBe('Accessibility analysis failed');
    });
  });

  describe('POST /analyse-url-flat', () => {
    it('returns 400 on SsrfGuardError', async () => {
      mockService.analyseUrlFlat.mockRejectedValue(new SsrfGuardError('Blocked IP'));
      const res = await request(app).post('/analyse-url-flat').send({ url: 'http://127.0.0.1' });
      expect(res.status).toBe(400);
      expect(res.body.error).toBe('Invalid URL');
    });

    it('returns 502 on certificate error', async () => {
      mockService.analyseUrlFlat.mockRejectedValue(new Error('ERR_CERT_AUTHORITY_INVALID'));
      const res = await request(app).post('/analyse-url-flat').send({ url: 'https://expired.com' });
      expect(res.status).toBe(502);
      expect(res.body.error).toBe('Target TLS certificate invalid');
    });
  });

  describe('POST /analyse-url', () => {
      it('returns 400 if url is missing', async () => {
          const res = await request(app).post('/analyse-url').send({});
          expect(res.status).toBe(400);
          expect(res.body.error).toContain('url field is required');
      });

      it('returns 400 if url is invalid', async () => {
          const res = await request(app).post('/analyse-url').send({ url: 'not-a-url' });
          expect(res.status).toBe(400);
          expect(res.body.error).toContain('url field is required');
      });

      it('returns 400 if protocol is unsupported', async () => {
          const res = await request(app).post('/analyse-url').send({ url: 'ftp://example.com' });
          expect(res.status).toBe(400);
          expect(res.body.error).toContain('url field is required');
      });

      it('returns 400 on SsrfGuardError', async () => {
          mockService.analyseUrl.mockRejectedValue(new SsrfGuardError('Blocked IP'));
          const res = await request(app).post('/analyse-url').send({ url: 'http://private.local' });
          expect(res.status).toBe(400);
          expect(res.body.error).toBe('Invalid URL');
      });
  });

  describe('POST /rules/:successCriteriaId/analyse-url', () => {
      it('returns 400 if successCriteriaId is malformed', async () => {
          const res = await request(app).post('/rules/invalid/analyse-url').send({ url: 'https://example.com' });
          expect(res.status).toBe(400);
          expect(res.body.error).toContain('successCriteriaId must match format');
      });

      it('returns 200 on success', async () => {
          mockService.analyseUrl.mockResolvedValue([]);
          const res = await request(app).post('/rules/1.1.1/analyse-url').send({ url: 'https://example.com' });
          expect(res.status).toBe(200);
          expect(res.body.url).toBe('https://example.com');
          expect(res.body.successCriteriaId).toBe('1.1.1');
      });
  });
});
