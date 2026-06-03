'use strict';

/**
 * @fileoverview Memory-bounded, same-hostname BFS crawl for the Node engine.
 *
 * The Node service historically audited only the single root URL — `maxDepth`
 * had no effect here, so a combined audit at depth>0 covered deep pages in
 * Python but not in Node. This helper gives Node its own bounded BFS so the two
 * engines crawl consistently.
 *
 * Mirrors the contract of the Python `a11y.crawler.bfs.bounded_bfs`:
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
/**
 * Resolve `promise` but reject with a timeout error after `ms` (when finite).
 * Used to keep the BFS loop responsive when a single page hangs.
 * @template T
 * @param {Promise<T>} promise
 * @param {number} ms          Timeout in ms; <= 0 or non-finite disables it.
 * @param {string} label
 * @returns {Promise<T>}
 */
function withTimeout(promise, ms, label) {
  if (!Number.isFinite(ms) || ms <= 0) return promise;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} (${Math.round(ms)}ms)`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function boundedBfs({
  baseUrl,
  maxDepth = 0,
  maxPages = 50,
  internalLinksOnly = true,
  visit,
  log = () => {},
  maxLinksPerPage = 200,
  // Overall wall-clock budget for the whole crawl. When exceeded the crawl
  // stops and returns the pages done so far — this MUST stay below the Python
  // caller's HTTP timeout so a deep crawl returns partial findings instead of
  // the caller timing out and discarding everything. 0 disables it.
  maxTotalMs = 0,
  // Hard cap for a single page's visit() so one hanging page can't consume the
  // whole budget. Clamped to the remaining overall budget. 0 disables it.
  perPageMs = 0,
}) {
  const baseHost = hostOf(baseUrl);
  const queue = [[baseUrl, 0]];
  const visited = new Set();
  let pagesDone = 0;

  const deadline = maxTotalMs > 0 ? Date.now() + maxTotalMs : Infinity;

  // Link-following is ALWAYS confined to the exact base hostname: we never follow
  // off-host links, so a deep crawl stays on the audited domain and cannot be used
  // to reach external/internal hosts via redirect-style hops (SSRF safety). The
  // `internalLinksOnly` flag is retained for API parity but only ever tightens —
  // it can never loosen — this same-host rule.
  void internalLinksOnly;
  const inScope = (url) => hostOf(url) === baseHost;

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

    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      log(`time budget reached (${maxTotalMs}ms) after ${pagesDone} page(s); ` +
          `stopping crawl with partial results`);
      break;
    }

    // Bound this page to the per-page cap, but never beyond the overall budget,
    // so the last page can't push total time past the deadline.
    const pageCap = Math.min(perPageMs > 0 ? perPageMs : Infinity, remaining);
    let links = [];
    try {
      links = (await withTimeout(visit(url, depth), pageCap, `page audit exceeded`)) || [];
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
