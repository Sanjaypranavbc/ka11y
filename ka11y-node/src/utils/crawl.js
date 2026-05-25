'use strict';

/**
 * @fileoverview Memory-bounded, same-hostname BFS crawl for the Node engine.
 *
 * The Node service historically audited only the single root URL — `maxDepth`
 * had no effect here, so a combined audit at depth>0 covered deep pages in
 * Python but not in Node. This helper gives Node its own bounded BFS so the two
 * engines crawl consistently.
 *
 * Mirrors the contract of the Python `ka11y.crawler.bfs.bounded_bfs`:
 *   - one shared `visited` set (no re-visits / cycles),
 *   - a hard `maxPages` ceiling so RAM/time stay bounded regardless of depth,
 *   - exact-hostname filtering when `internalLinksOnly` ("internal links only"),
 *   - the caller's `visit(url, depth)` does the per-page work and returns hrefs.
 */

/**
 * Normalize a URL for dedup: lowercase host, drop fragment, strip a trailing
 * slash. Returns '' for anything unparseable or non-http(s).
 * @param {string} raw
 * @returns {string}
 */
function normalizeUrl(raw) {
  if (!raw || typeof raw !== 'string') return '';
  let u;
  try {
    u = new URL(raw);
  } catch {
    return '';
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return '';
  u.hash = '';
  let s = u.toString();
  // Strip a single trailing slash on the path (but keep "https://host/")
  if (s.endsWith('/') && u.pathname !== '/') s = s.slice(0, -1);
  return s;
}

/**
 * Hostname of a URL, lowercased; '' if unparseable.
 * @param {string} raw
 * @returns {string}
 */
function hostOf(raw) {
  try {
    return new URL(raw).hostname.toLowerCase();
  } catch {
    return '';
  }
}

/**
 * Run a memory-bounded, same-hostname BFS.
 *
 * @param {object}   opts
 * @param {string}   opts.baseUrl            Root URL; also the origin links are filtered against.
 * @param {number}   opts.maxDepth           Max link depth to follow (0 = root only).
 * @param {number}   opts.maxPages           Hard page budget (RAM/time ceiling).
 * @param {boolean}  opts.internalLinksOnly  Exact-hostname filter (domain-specific links only).
 * @param {(url:string, depth:number) => Promise<string[]>} opts.visit
 *        Audits one page and returns the hrefs found on it.
 * @param {(msg:string)=>void} [opts.log]
 * @param {number}   [opts.maxLinksPerPage=200] Cap on links enqueued per page.
 * @returns {Promise<number>} number of pages actually visited
 */
async function boundedBfs({
  baseUrl,
  maxDepth = 0,
  maxPages = 50,
  internalLinksOnly = true,
  visit,
  log = () => {},
  maxLinksPerPage = 200,
}) {
  const baseHost = hostOf(baseUrl);
  const queue = [[baseUrl, 0]];
  const visited = new Set();
  let pagesDone = 0;

  const inScope = (url) => !internalLinksOnly || hostOf(url) === baseHost;

  while (queue.length > 0) {
    const [rawUrl, depth] = queue.shift();
    const url = normalizeUrl(rawUrl);
    if (!url || visited.has(url)) continue;
    visited.add(url);

    if (!inScope(url)) continue; // off-host link → skipped when internal-only

    if (pagesDone >= maxPages) {
      log(`page budget reached (${maxPages}); stopping crawl`);
      break;
    }

    let links = [];
    try {
      links = (await visit(url, depth)) || [];
    } catch (e) {
      log(`error visiting ${url}: ${e.message}`);
      links = [];
    }
    pagesDone += 1;

    if (depth < maxDepth) {
      let enqueued = 0;
      for (const href of links) {
        if (enqueued >= maxLinksPerPage) break;
        const next = normalizeUrl(href);
        if (next && !visited.has(next) && inScope(next)) {
          queue.push([next, depth + 1]);
          enqueued += 1;
        }
      }
    }
  }

  log(`crawl complete: ${pagesDone} page(s) visited`);
  return pagesDone;
}

module.exports = { boundedBfs, normalizeUrl, hostOf };
