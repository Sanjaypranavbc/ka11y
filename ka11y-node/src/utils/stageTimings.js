/**
 * src/utils/stageTimings.js
 * =========================
 * Per-request collector for low-level per-(page, stage, sub_stage) timing rows.
 *
 * Node and Python share a single JSONL log file (one per audit run) so the
 * combined timing summary can attribute time to either engine. But Node runs
 * inside a separate Docker container with no shared volume, so we don't write
 * to disk on this side. Instead each `/api/v1/analyse-url-flat` request
 * accumulates rows on a per-request `StageTimings` instance, and the Python
 * caller appends those rows to its own JSONL via `stage_timing.record(...)`.
 *
 * Row schema mirrors the Python `stage_timing` module exactly:
 *
 *     {
 *       ts:          "2026-05-29T10:42:18.731Z",
 *       page_url:    "https://example.com/child" | null,
 *       depth:       1 | null,
 *       stage:       "axe_core",
 *       sub_stage:   "page_navigate" | "axe_run" | "custom_checks" | "result_mapping",
 *       rule:        "1.4.3" | null,
 *       duration_ms: 123.4,
 *       item_count:  42 | null,
 *       status:      "ok" | "error",
 *       error:       null | "msg",
 *       extra:       {...}
 *     }
 *
 * Safety: every call is wrapped in try/finally and never throws. A logging bug
 * must never break an axe run.
 */

'use strict';

class StageTimings {
  constructor({ enabled = true } = {}) {
    this.enabled = enabled;
    this.rows = [];
  }

  record({
    stage,
    sub_stage = null,
    page_url = null,
    depth = null,
    rule = null,
    duration_ms = 0,
    item_count = null,
    status = 'ok',
    error = null,
    extra = null,
  }) {
    if (!this.enabled) return;
    try {
      this.rows.push({
        ts: new Date().toISOString(),
        page_url,
        depth,
        stage,
        sub_stage,
        rule,
        duration_ms: Math.round(duration_ms * 1000) / 1000,
        item_count,
        status,
        error,
        extra: extra || {},
        source: 'node',
      });
    } catch {
      // Swallow — recording must never break audit flow.
    }
  }

  /**
   * Time an async function and record one row. Records "error" status if the
   * function throws, then re-raises so callers see the original failure.
   */
  async time({ stage, sub_stage = null, page_url = null, depth = null, rule = null, extra = null }, fn) {
    if (!this.enabled) return fn();
    const t0 = process.hrtime.bigint();
    let status = 'ok';
    let err = null;
    try {
      return await fn();
    } catch (e) {
      status = 'error';
      err = (e && e.message) ? String(e.message).slice(0, 200) : String(e).slice(0, 200);
      throw e;
    } finally {
      const ns = Number(process.hrtime.bigint() - t0);
      const duration_ms = ns / 1e6;
      this.record({
        stage,
        sub_stage,
        page_url,
        depth,
        rule,
        duration_ms,
        status,
        error: err,
        extra,
      });
    }
  }

  toArray() {
    return this.rows.slice();
  }
}

/** No-op instance used when a caller didn't supply a real collector. */
const NULL_TIMINGS = new StageTimings({ enabled: false });

module.exports = { StageTimings, NULL_TIMINGS };
