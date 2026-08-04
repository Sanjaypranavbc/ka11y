'use strict';

/**
 * @fileoverview Sitemap-driven page discovery for /analyse-url-wcag's `maxDepth`.
 *
 * Unlike `crawl.js` (link-following BFS used by the flat/crawl endpoints),
 * this resolves the *page list* to scan straight from the site's sitemap.xml
 * (following a sitemap index one level deep, and falling back to the
 * `Sitemap:` directive in robots.txt) so `maxDepth` reads as "how many extra
 * pages from the sitemap" rather than "how many link-hops to follow".
 */

const FETCH_TIMEOUT_MS = 8_000;
const MAX_SITEMAP_INDEX_CHILDREN = 3; // cap fan-out when a sitemap is itself an index
const MAX_URLS_RETURNED = 200; // hard ceiling regardless of requested depth

async function _fetchText(url, { assertPublicUrl }) {
  await assertPublicUrl(url);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      redirect: 'follow',
      headers: { 'User-Agent': 'ka11y-accessibility-auditor' },
    });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function _extractLocs(xml) {
  if (!xml) return [];
  const matches = xml.match(/<loc>\s*([^<\s][^<]*?)\s*<\/loc>/gi) || [];
  return matches
    .map((tag) => tag.replace(/<\/?loc>/gi, '').trim())
    .filter(Boolean);
}

function _isSitemapIndex(xml) {
  return /<sitemapindex[\s>]/i.test(xml || '');
}

/**
 * Discover page URLs for a site's sitemap, same-hostname only, base URL first.
 *
 * @param {string} baseUrl
 * @param {object} deps
 * @param {(url: string) => Promise<void>} deps.assertPublicUrl  SSRF guard (throws on private/unresolvable hosts)
 * @param {object} [deps.logger]
 * @returns {Promise<string[]>} deduped, same-host URLs (base URL first, then sitemap order)
 */
async function getSitemapUrls(baseUrl, { assertPublicUrl, logger } = {}) {
  const log = logger || { warn: () => {}, info: () => {} };
  let origin, baseHost;
  try {
    const parsed = new URL(baseUrl);
    origin = parsed.origin;
    baseHost = parsed.hostname.toLowerCase();
  } catch {
    return [baseUrl];
  }

  const candidateSitemaps = [`${origin}/sitemap.xml`];

  const robotsText = await _fetchText(`${origin}/robots.txt`, { assertPublicUrl }).catch(() => null);
  if (robotsText) {
    const lines = robotsText.split(/\r?\n/);
    for (const line of lines) {
      const m = line.match(/^\s*sitemap\s*:\s*(\S+)/i);
      if (m && m[1]) candidateSitemaps.push(m[1].trim());
    }
  }

  const seenLocs = new Set();
  const locs = [];

  for (const sitemapUrl of candidateSitemaps) {
    let xml;
    try {
      xml = await _fetchText(sitemapUrl, { assertPublicUrl });
    } catch (err) {
      log.warn(`getSitemapUrls: skipping ${sitemapUrl}: ${err.message}`);
      continue;
    }
    if (!xml) continue;

    if (_isSitemapIndex(xml)) {
      const childSitemaps = _extractLocs(xml).slice(0, MAX_SITEMAP_INDEX_CHILDREN);
      for (const child of childSitemaps) {
        let childXml;
        try {
          childXml = await _fetchText(child, { assertPublicUrl });
        } catch (err) {
          log.warn(`getSitemapUrls: skipping child sitemap ${child}: ${err.message}`);
          continue;
        }
        for (const loc of _extractLocs(childXml)) {
          if (!seenLocs.has(loc)) { seenLocs.add(loc); locs.push(loc); }
        }
      }
    } else {
      for (const loc of _extractLocs(xml)) {
        if (!seenLocs.has(loc)) { seenLocs.add(loc); locs.push(loc); }
      }
    }

    if (locs.length > 0) break; // first sitemap that yields URLs wins
  }

  const sameHost = locs.filter((u) => {
    try { return new URL(u).hostname.toLowerCase() === baseHost; } catch { return false; }
  });

  // Base URL always first, then sitemap order, deduped, capped.
  const ordered = [baseUrl, ...sameHost.filter((u) => u !== baseUrl)];
  const deduped = [...new Set(ordered)];
  return deduped.slice(0, MAX_URLS_RETURNED);
}

module.exports = { getSitemapUrls };
