'use strict';

const { boundedBfs, normalizeUrl, hostOf } = require('../../src/utils/crawl');

describe('normalizeUrl', () => {
  test('strips fragment and a trailing slash, lowercases host', () => {
    expect(normalizeUrl('https://Example.com/a/#frag')).toBe('https://example.com/a');
  });
  test('keeps the root "/" path', () => {
    expect(normalizeUrl('https://example.com')).toBe('https://example.com/');
    expect(normalizeUrl('https://example.com/')).toBe('https://example.com/');
  });
  test('rejects unparseable and non-http(s) URLs', () => {
    expect(normalizeUrl('not a url')).toBe('');
    expect(normalizeUrl('ftp://example.com/x')).toBe('');
    expect(normalizeUrl('')).toBe('');
  });
});

describe('hostOf', () => {
  test('returns lowercased hostname, or "" for junk', () => {
    expect(hostOf('https://Example.com/x')).toBe('example.com');
    expect(hostOf('garbage')).toBe('');
  });
});

describe('boundedBfs', () => {
  test('maxDepth=0 visits only the root, even when it links elsewhere', async () => {
    const visited = [];
    const n = await boundedBfs({
      baseUrl: 'https://example.com',
      maxDepth: 0,
      visit: async (url) => { visited.push(url); return ['https://example.com/a', 'https://example.com/b']; },
    });
    expect(n).toBe(1);
    expect(visited).toEqual(['https://example.com/']);
  });

  test('maxDepth=1 follows one level of same-host links and skips off-host links', async () => {
    const visited = [];
    const links = {
      'https://example.com/': ['https://example.com/a', 'https://evil.com/x', 'https://example.com/b'],
      'https://example.com/a': ['https://example.com/c'], // depth 2 — must NOT be visited
    };
    const n = await boundedBfs({
      baseUrl: 'https://example.com',
      maxDepth: 1,
      visit: async (url) => { visited.push(url); return links[url] || []; },
    });
    expect(visited).toEqual([
      'https://example.com/',
      'https://example.com/a',
      'https://example.com/b',
    ]);
    expect(n).toBe(3);
    expect(visited).not.toContain('https://evil.com/x');
    expect(visited).not.toContain('https://example.com/c');
  });

  test('maxPages bounds the crawl regardless of how many links exist (RAM ceiling)', async () => {
    const visited = [];
    const n = await boundedBfs({
      baseUrl: 'https://example.com',
      maxDepth: 5,
      maxPages: 3,
      // Every page fans out to 10 fresh same-host links → unbounded without the cap.
      visit: async (url) => {
        visited.push(url);
        return Array.from({ length: 10 }, (_, i) => `${url.replace(/\/$/, '')}/p${visited.length}-${i}`);
      },
    });
    expect(n).toBe(3);
    expect(visited).toHaveLength(3);
  });

  test('stays on the base host even when internalLinksOnly is false (safeguard)', async () => {
    const visited = [];
    await boundedBfs({
      baseUrl: 'https://example.com',
      maxDepth: 2,
      internalLinksOnly: false,
      visit: async (url) => { visited.push(url); return ['https://evil.com/x', 'https://example.com/a']; },
    });
    expect(visited).toContain('https://example.com/');
    expect(visited).toContain('https://example.com/a');
    expect(visited.every(u => hostOf(u) === 'example.com')).toBe(true);
    expect(visited).not.toContain('https://evil.com/x');
  });

  test('a link cycle does not cause an infinite loop', async () => {
    const visited = [];
    const links = {
      'https://example.com/': ['https://example.com/a'],
      'https://example.com/a': ['https://example.com/'], // back-edge
    };
    const n = await boundedBfs({
      baseUrl: 'https://example.com',
      maxDepth: 10,
      visit: async (url) => { visited.push(url); return links[url] || []; },
    });
    expect(n).toBe(2);
    expect(visited).toEqual(['https://example.com/', 'https://example.com/a']);
  });
});
