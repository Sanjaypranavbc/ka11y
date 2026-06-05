'use strict';

const request = require('supertest');
const app     = require('../server');

describe('GET /rules-guide', () => {
  it('returns 200 with total and rules array', async () => {
    const res = await request(app).get('/rules-guide');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('total');
    expect(typeof res.body.total).toBe('number');
    expect(Array.isArray(res.body.rules)).toBe(true);
    expect(res.body.total).toBe(res.body.rules.length);
  });

  it('each rule has required fields', async () => {
    const res = await request(app).get('/rules-guide');
    expect(res.body.rules.length).toBeGreaterThan(0);
    for (const rule of res.body.rules) {
      expect(rule).toHaveProperty('ruleId');
      expect(rule).toHaveProperty('title');
      expect(rule).toHaveProperty('wcagLevel');
      expect(rule).toHaveProperty('guidance');
      expect(rule).toHaveProperty('howToTest');
      expect(rule).toHaveProperty('failExample');
      expect(rule).toHaveProperty('passExample');
      expect(rule).toHaveProperty('fixTip');
    }
  });

  it('filters by wcagLevel=A', async () => {
    const res = await request(app).get('/rules-guide?wcagLevel=A');
    expect(res.status).toBe(200);
    expect(res.body.rules.length).toBeGreaterThan(0);
    res.body.rules.forEach(r => expect(r.wcagLevel).toBe('A'));
  });

  it('filters by wcagLevel=AA', async () => {
    const res = await request(app).get('/rules-guide?wcagLevel=AA');
    expect(res.status).toBe(200);
    res.body.rules.forEach(r => expect(r.wcagLevel).toBe('AA'));
  });

  it('filters by wcagLevel=best-practice', async () => {
    const res = await request(app).get('/rules-guide?wcagLevel=best-practice');
    expect(res.status).toBe(200);
    expect(res.body.rules.length).toBeGreaterThan(0);
    res.body.rules.forEach(r => expect(r.wcagLevel).toBe('best-practice'));
  });

  it('filters by successCriteriaId=1.1.1', async () => {
    const res = await request(app).get('/rules-guide?successCriteriaId=1.1.1');
    expect(res.status).toBe(200);
    expect(res.body.rules.length).toBeGreaterThan(0);
    res.body.rules.forEach(r => expect(r.successCriteriaId).toBe('1.1.1'));
  });

  it('returns fewer rules when filtering vs unfiltered', async () => {
    const allRes  = await request(app).get('/rules-guide');
    const filtRes = await request(app).get('/rules-guide?wcagLevel=A');
    expect(filtRes.body.total).toBeLessThan(allRes.body.total);
  });

  it('returns empty rules array for unknown wcagLevel', async () => {
    const res = await request(app).get('/rules-guide?wcagLevel=UNKNOWN');
    expect(res.status).toBe(200);
    expect(res.body.total).toBe(0);
    expect(res.body.rules).toEqual([]);
  });
});

describe('GET /rules-guide/:ruleId', () => {
  it('returns 200 with rule data for a known ruleId', async () => {
    const res = await request(app).get('/rules-guide/image-alt');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('ruleId', 'image-alt');
    expect(res.body).toHaveProperty('title');
    expect(res.body).toHaveProperty('wcagLevel');
    expect(res.body).toHaveProperty('guidance');
  });

  it('returns 404 for an unknown ruleId', async () => {
    const res = await request(app).get('/rules-guide/not-a-real-rule');
    expect(res.status).toBe(404);
    expect(res.body).toHaveProperty('error', 'Rule not found');
    expect(res.body).toHaveProperty('message');
  });

  it('ruleId in response matches the requested path param', async () => {
    const res = await request(app).get('/rules-guide/accesskeys');
    expect(res.status).toBe(200);
    expect(res.body.ruleId).toBe('accesskeys');
  });
});
