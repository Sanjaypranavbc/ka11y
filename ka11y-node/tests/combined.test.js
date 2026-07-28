'use strict';

const request = require('supertest');
const express = require('express');
const app = require('../server');

describe('Combined API Endpoint', () => {
  it('returns 400 if url is missing', async () => {
    const res = await request(app).get('/api/ka11y/combined');
    expect(res.status).toBe(400);
    expect(res.body.error).toContain('url parameter is required');
  });

  it('returns 400 if url is malformed', async () => {
    const res = await request(app).get('/api/ka11y/combined?url=not-a-url');
    expect(res.status).toBe(400);
    expect(res.body.error).toContain('url must be a valid fully-qualified HTTP/HTTPS URL');
  });
});
