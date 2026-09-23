"use strict";

/**
 * flashAnalysis.js — general flash measurement of the live page (WCAG 2.3.1 / 2.3.2, G19 / G15 / G176).
 *
 * CSS keyframe inspection only sees declared animations. JavaScript, canvas, WebGL, animated
 * GIF and <video> flashing are only visible on screen, so this helper records a short CDP
 * screencast (Page.startScreencast), sends each JPEG frame back into the page where it is
 * decoded on a canvas and reduced to a 32×18 luminance grid, then counts opposing relative
 * luminance transitions (≥ 10 %, darker side < 0.80) per cell and per one-second window.
 *
 * Returns null when the page object has no CDP session (unit tests, mocks).
 */

const GRID_W = 32;
const GRID_H = 18;
const CAPTURE_MS = 2500;
const MAX_FRAMES = 40;
// ≈ 25 % of a 10° field on a 1024×768 display, as a fraction of the viewport
const GENERAL_AREA_THRESHOLD = 0.028;

async function captureFlashProfile(page, opts = {}) {
  if (!page || typeof page.createCDPSession !== 'function' || typeof page.evaluate !== 'function') return null;
  let client = null;
  let meta = null;
  const frames = [];
  const times = [];
  try {
    client = await page.createCDPSession();
    const onFrame = async (ev) => {
      try {
        if (ev.metadata && !meta) meta = ev.metadata;
        if (frames.length < MAX_FRAMES) { frames.push(ev.data); times.push(ev.metadata && ev.metadata.timestamp ? ev.metadata.timestamp * 1000 : Date.now()); }
        await client.send('Page.screencastFrameAck', { sessionId: ev.sessionId });
      } catch (_) { /* ignore */ }
    };
    client.on('Page.screencastFrame', onFrame);
    await client.send('Page.startScreencast', { format: 'jpeg', quality: 35, maxWidth: 320, maxHeight: 200, everyNthFrame: 1 });
    await new Promise(r => setTimeout(r, CAPTURE_MS));
    await client.send('Page.stopScreencast').catch(() => {});
    client.off('Page.screencastFrame', onFrame);
  } catch (_) {
    return null;
  } finally {
    if (client) { try { await client.detach(); } catch (_) { /* ignore */ } }
  }
  if (frames.length < 4) return { frames: frames.length, maxFlashesPerSecond: 0, flashingArea: 0, cells: [], coverage: 0 };

  const grids = await page.evaluate(async (dataUrls, gw, gh) => {
    const out = [];
    const c = document.createElement('canvas'); c.width = gw; c.height = gh;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    for (const b64 of dataUrls) {
      try {
        const blob = await (await fetch('data:image/jpeg;base64,' + b64)).blob();
        const bmp = await createImageBitmap(blob);
        ctx.drawImage(bmp, 0, 0, gw, gh);
        const d = ctx.getImageData(0, 0, gw, gh).data;
        const g = new Array(gw * gh);
        for (let i = 0; i < gw * gh; i++) {
          const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
          g[i] = 0.2126 * lin(d[i * 4]) + 0.7152 * lin(d[i * 4 + 1]) + 0.0722 * lin(d[i * 4 + 2]);
        }
        out.push(g);
        bmp.close && bmp.close();
      } catch (_) { out.push(null); }
    }
    return out;
  }, frames, GRID_W, GRID_H).catch(() => null);
  if (!Array.isArray(grids)) return null;
  const valid = grids.map((g, i) => [g, times[i]]).filter(x => Array.isArray(x[0]));
  if (valid.length < 4) return { frames: valid.length, maxFlashesPerSecond: 0, flashingArea: 0, cells: [] };

  const span = Math.max(1, (valid[valid.length - 1][1] - valid[0][1]) / 1000);
  const fps = valid.length / span;
  const nCells = GRID_W * GRID_H;
  let flashingCells = 0;
  let maxRate = 0;
  const cells = [];
  for (let c = 0; c < nCells; c++) {
    // significant transitions with sign
    const trans = [];
    for (let f = 1; f < valid.length; f++) {
      const a = valid[f - 1][0][c], b = valid[f][0][c];
      const diff = b - a;
      if (Math.abs(diff) >= 0.10 && Math.min(a, b) < 0.80) trans.push({ t: valid[f][1], s: Math.sign(diff) });
    }
    if (trans.length < 2) continue;
    // opposing pairs within any 1 s window
    let best = 0;
    for (let i = 0; i < trans.length; i++) {
      let pairs = 0, last = trans[i].s;
      for (let j = i + 1; j < trans.length && trans[j].t - trans[i].t <= 1000; j++) { if (trans[j].s !== last) { pairs++; last = trans[j].s; } }
      best = Math.max(best, Math.floor((pairs + 1) / 2));
    }
    if (best > 3) { flashingCells++; cells.push({ x: c % GRID_W, y: Math.floor(c / GRID_W), flashes: best }); }
    maxRate = Math.max(maxRate, best);
  }
  // The screencast shows the real browser window; when it is smaller than the emulated
  // viewport (headless default 800×600), only part of the page is measured — report it.
  let coverage = 1;
  try {
    const vp = typeof page.viewport === 'function' ? page.viewport() : null;
    if (vp && meta && meta.deviceWidth && meta.deviceHeight) coverage = Math.min(1, (meta.deviceWidth * meta.deviceHeight) / (vp.width * vp.height));
  } catch (_) { /* ignore */ }
  const result = { frames: valid.length, fps: Math.round(fps * 10) / 10, maxFlashesPerSecond: maxRate, flashingArea: Math.round((flashingCells / nCells) * 10000) / 10000, cells: cells.slice(0, 20), coverage: Math.round(coverage * 100) / 100, captured: meta ? { width: meta.deviceWidth, height: meta.deviceHeight } : null };
  if (opts && opts.debug) {
    const variance = [];
    for (let c = 0; c < nCells; c++) { const v = valid.map(x => x[0][c]); const mean = v.reduce((a, b) => a + b, 0) / v.length; variance.push([v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length, c]); }
    variance.sort((a, b) => b[0] - a[0]);
    result.debug = { spanMs: valid[valid.length - 1][1] - valid[0][1], top: variance.slice(0, 3).map(([vr, c]) => ({ cell: c, x: c % GRID_W, y: Math.floor(c / GRID_W), variance: +vr.toFixed(4), series: valid.map(x => +x[0][c].toFixed(2)).slice(0, 25) })) };
  }
  return result;
}

module.exports = { captureFlashProfile, GENERAL_AREA_THRESHOLD };
