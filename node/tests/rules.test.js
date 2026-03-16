'use strict';

const request = require('supertest');
const app     = require('../server');

describe('GET /rules', () => {
  it('returns 200 with correct top-level shape', async () => {
    const res = await request(app).get('/rules');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('standard', 'WCAG 2.1');
    expect(res.body).toHaveProperty('total_rules');
    expect(res.body).toHaveProperty('ruleslist');
    expect(res.body).toHaveProperty('criteria');
    expect(typeof res.body.criteria).toBe('object');
  });

  it('returns rules grouped under numeric criteria keys (e.g. "1.1.1")', async () => {
    const res = await request(app).get('/rules');
    const keys = Object.keys(res.body.criteria);
    expect(keys.length).toBeGreaterThan(0);
    keys.forEach(key => expect(key).toMatch(/^\d+\.\d+\.\d+$/));
  });

  it('each criterion contains a name and a rules array', async () => {
    const res = await request(app).get('/rules');
    for (const [, value] of Object.entries(res.body.criteria)) {
      expect(value).toHaveProperty('name');
      expect(Array.isArray(value.rules)).toBe(true);
      expect(value.rules.length).toBeGreaterThan(0);
      value.rules.forEach(rule => {
        expect(rule).toHaveProperty('rule_id');
        expect(rule).toHaveProperty('description');
        expect(rule).toHaveProperty('help_url');
      });
    }
  });

  it('filters by single tag query parameter', async () => {
    const res = await request(app).get('/rules?tags=wcag2a');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('criteria');
    expect(res.body.total_rules).toBeGreaterThan(0);
  });

  it('filters by multiple comma-separated tags', async () => {
    const res = await request(app).get('/rules?tags=wcag2a,wcag2aa');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('criteria');
  });

  it('returns fewer rules when filtering by a narrower tag set', async () => {
    const allRes  = await request(app).get('/rules');
    const filtRes = await request(app).get('/rules?tags=wcag2a');
    expect(filtRes.body.total_rules).toBeLessThanOrEqual(allRes.body.total_rules);
  });
});
