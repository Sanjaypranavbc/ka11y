'use strict';

/**
 * selftest.js — Axe-core rule coverage self-test.
 *
 * Sends a comprehensive HTML fixture (intentionally violating as many
 * axe-core rules as possible) to the running API and reports which rules
 * were detected (fail / incomplete / pass) vs. not observed (inapplicable).
 *
 * Usage:
 *   node selftest.js
 *   node selftest.js --port 3000   (default)
 *
 * Rules NOT reachable with the current API runOnly config
 * (['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']):
 *   • Deprecated    : aria-roledescription, audio-caption,
 *                     duplicate-id-active, duplicate-id
 *   • WCAG AAA only : color-contrast-enhanced, identical-links-same-purpose,
 *                     meta-refresh-no-exceptions
 *   • WCAG 2.2 only : target-size
 */

const http = require('http');
const axe  = require('axe-core');

const PORT = (() => {
  const idx = process.argv.indexOf('--port');
  return idx !== -1 ? parseInt(process.argv[idx + 1]) : 3000;
})();

// ─── All rule IDs from axe-core ─────────────────────────────────────────────
const ALL_RULES = axe.getRules().map(r => r.ruleId);

// Rules that will NEVER be observed given the API's current runOnly config.
// Used to annotate the "not observed" section with a clear reason.
const UNREACHABLE = {
  deprecated: new Set([
    'aria-roledescription', 'audio-caption', 'duplicate-id-active', 'duplicate-id',
  ]),
  wcagAaa: new Set([
    'color-contrast-enhanced', 'identical-links-same-purpose', 'meta-refresh-no-exceptions',
  ]),
  wcag22: new Set(['target-size']),
};

// ─── Comprehensive "bad" HTML fixture ───────────────────────────────────────
// Each block is labelled with the axe rule(s) it targets.
const BAD_HTML = `<!DOCTYPE html>
<html lang="xx-invalid">
<!-- html-lang-valid: "xx-invalid" is not a valid BCP-47 language tag -->
<head>
  <!-- document-title: no <title> element present -->

  <!-- meta-refresh: value 7200 is under the 72000-second threshold axe flags;
       large enough to avoid a real navigation during the test -->
  <meta http-equiv="refresh" content="7200">

  <!-- meta-viewport: user-scalable=no disables pinch-zoom -->
  <!-- meta-viewport-large: maximum-scale=2 is less than 5 -->
  <meta name="viewport" content="user-scalable=no, maximum-scale=2">
</head>
<body>

  <!-- ── skip-link: first focusable link points to a nonexistent anchor ── -->
  <a href="#nonexistent-skip-target">Skip to main content</a>

  <!-- ── accesskeys: two elements share accesskey "a" ── -->
  <button accesskey="a">Button A1</button>
  <a href="#" accesskey="a">Link A2</a>

  <!-- ── area-alt: <area> has no alt attribute ── -->
  <img src="map.png" usemap="#testmap" alt="Image map">
  <map name="testmap">
    <area shape="rect" coords="0,0,10,10" href="#">
  </map>

  <!-- ── aria-allowed-attr: aria-checked is not valid on role=link ── -->
  <a href="#" aria-checked="true">Link with invalid aria-checked</a>

  <!-- ── aria-braille-equivalent: aria-braillelabel without aria-label ── -->
  <button aria-braillelabel="btn">Braille btn</button>

  <!-- ── aria-command-name: role=link / role=menuitem with no accessible name ── -->
  <span role="link" tabindex="0"></span>
  <span role="menuitem"></span>

  <!-- ── aria-input-field-name: role=textbox with no accessible name ── -->
  <span role="textbox" tabindex="0"></span>

  <!-- ── aria-text: role="text" on a focusable element ── -->
  <span role="text"><a href="#aria-text-target">Link inside role=text</a></span>

  <!-- ── aria-allowed-role: role=heading is not allowed on <input> ── -->
  <label for="role-input">Role input</label>
  <input type="text" id="role-input" role="heading">

  <!-- ── aria-deprecated-role: "directory" role is deprecated ── -->
  <div role="directory">Directory role</div>

  <!-- ── aria-dialog-name: dialog without accessible name ── -->
  <div role="dialog">Nameless dialog</div>

  <!-- ── aria-hidden-focus: focusable element inside aria-hidden ── -->
  <div aria-hidden="true">
    <button>Hidden but focusable</button>
  </div>

  <!-- ── aria-meter-name: role=meter without accessible name ── -->
  <div role="meter" aria-valuenow="50" aria-valuemin="0" aria-valuemax="100">50%</div>

  <!-- ── aria-progressbar-name: role=progressbar without accessible name ── -->
  <div role="progressbar" aria-valuenow="50" aria-valuemin="0" aria-valuemax="100">50%</div>

  <!-- ── aria-prohibited-attr: aria-label on role=none ── -->
  <p role="none" aria-label="has label">Paragraph</p>

  <!-- ── aria-required-attr: role=checkbox without required aria-checked ── -->
  <div role="checkbox" id="check-noattr">Missing aria-checked</div>

  <!-- ── aria-required-children: role=list without listitem children ── -->
  <div role="list"><div>Not a listitem</div></div>

  <!-- ── aria-required-parent: listitem outside a list context ── -->
  <div role="listitem">Orphan listitem</div>

  <!-- ── aria-roles: completely invalid ARIA role name ── -->
  <div role="notarealrole">Invalid role</div>

  <!-- ── aria-toggle-field-name: role=switch without accessible name ── -->
  <div role="switch" aria-checked="false"></div>

  <!-- ── aria-tooltip-name: role=tooltip without accessible name ── -->
  <div role="tooltip"></div>

  <!-- ── aria-treeitem-name: treeitem without accessible name ── -->
  <div role="tree"><div role="treeitem"></div></div>

  <!-- ── aria-valid-attr: "aria-fake" is not a real ARIA attribute ── -->
  <div aria-fake="true">Invalid ARIA attribute name</div>

  <!-- ── aria-valid-attr-value: "badvalue" is not valid for aria-live ── -->
  <div aria-live="badvalue">Invalid aria-live value</div>

  <!-- ── autocomplete-valid: "bad-value" is not a valid autocomplete token ── -->
  <label for="ac-input">Name</label>
  <input id="ac-input" type="text" autocomplete="bad-value">

  <!-- ── avoid-inline-spacing: !important on text-spacing CSS properties ── -->
  <p style="letter-spacing:0!important; word-spacing:0!important; line-height:1!important;">
    Forced spacing override
  </p>

  <!-- ── blink: deprecated <blink> element ── -->
  <blink>Blinking text</blink>

  <!-- ── button-name: button with no accessible name ── -->
  <button></button>

  <!-- ── color-contrast: contrast ratio ~2.32:1 (needs 4.5:1) ── -->
  <p style="color:#aaaaaa; background-color:#ffffff;">Low contrast text</p>

  <!-- ── definition-list: <li> is an invalid direct child of <dl> ── -->
  <dl><li>Invalid dl child</li></dl>

  <!-- ── dlitem: <dt> and <dd> outside a <dl> ── -->
  <dt>Orphan dt</dt>
  <dd>Orphan dd</dd>

  <!-- ── duplicate-id-aria: duplicate IDs used with aria-labelledby ── -->
  <div id="dupid">First element</div>
  <div id="dupid">Second element</div>
  <div aria-labelledby="dupid">References duplicate ID</div>

  <!-- ── empty-heading: <h4> with no text content ── -->
  <!-- (Placed AFTER h1→h3 so it does not fill the skipped h2 slot) -->
  <h1>Page Heading</h1>
  <h3>Skipped h2 level</h3>
  <!-- ── heading-order: h1 jumps directly to h3, skipping h2 ── -->
  <h4></h4>

  <!-- ── empty-table-header: <th> with no content ── -->
  <table>
    <tr><th></th><td>Data</td></tr>
  </table>

  <!-- ── focus-order-semantics: non-interactive <span> made focusable ── -->
  <span tabindex="0">Focusable non-interactive span</span>

  <!-- ── form-field-multiple-labels: explicit <label> AND aria-label on same input ── -->
  <label for="multi">Primary label</label>
  <input id="multi" type="text" aria-label="Secondary label">

  <!-- ── frame-focusable-content: iframe with tabindex=-1 that holds a focusable button ── -->
  <iframe tabindex="-1" src="data:text/html,<button>Focusable inside iframe</button>"></iframe>

  <!-- ── frame-title: <iframe> without a title attribute ── -->
  <iframe src="about:blank"></iframe>

  <!-- ── frame-title-unique: two iframes with the identical title ── -->
  <iframe title="Duplicate Frame" src="about:blank"></iframe>
  <iframe title="Duplicate Frame" src="about:blank"></iframe>

  <!-- ── hidden-content: display:none content for review ── -->
  <div style="display:none"><p>Hidden content that needs accessibility review</p></div>

  <!-- ── image-alt: <img> without alt attribute ── -->
  <img src="logo.png">

  <!-- ── image-redundant-alt: alt text is repeated verbatim as link text ── -->
  <a href="#"><img src="company.png" alt="Company Logo"> Company Logo</a>

  <!-- ── input-button-name: <input type=button> with empty value ── -->
  <input type="button" value="">

  <!-- ── input-image-alt: <input type=image> without alt ── -->
  <input type="image" src="submit.png">

  <!-- ── label: text input with no associated label ── -->
  <input type="text" id="unlabeled">

  <!-- ── label-content-name-mismatch: aria-label does not contain visible text ── -->
  <button aria-label="Go away">Submit</button>

  <!-- ── label-title-only: form field labeled only via title attribute ── -->
  <input type="text" id="title-label" title="Title Only Label">

  <!-- ── link-in-text-block: link distinguished from surrounding text only by colour ── -->
  <p style="background:#fff; color:#000;">
    Paragraph text with
    <a href="#color-only" style="color:red; text-decoration:none;">inline link</a>
    only distinguished by colour.
  </p>

  <!-- ── list: <div> is an invalid direct child of <ul> ── -->
  <ul><div>Invalid ul child</div></ul>

  <!-- ── listitem: <li> outside a list element ── -->
  <li>Orphan li</li>

  <!-- ── marquee: deprecated <marquee> element ── -->
  <marquee>Scrolling content</marquee>

  <!-- ── nested-interactive: <div role=button> wrapping a real <a> ──
       Using ARIA role avoids browser auto-correction of nested native elements -->
  <div role="button" tabindex="0"><a href="#nested">Link inside button role</a></div>

  <!-- ── no-autoplay-audio: autoplay + loop implies indefinite duration ── -->
  <audio autoplay loop><source src="audio.mp3" type="audio/mpeg"></audio>

  <!-- ── object-alt: <object> without accessible name ── -->
  <object data="file.swf" type="application/x-shockwave-flash" width="50" height="50"></object>

  <!-- ── p-as-heading: large bold paragraph that visually mimics a heading ── -->
  <p style="font-size:2em; font-weight:bold;">Section Title As Paragraph</p>

  <!-- ── presentation-role-conflict: tabbable <a> with role=presentation ── -->
  <a href="#" role="presentation">Tabbable with presentation role</a>

  <!-- ── role-img-alt: role=img without accessible name ── -->
  <div role="img">Image without alt</div>

  <!-- ── scope-attr-valid: invalid scope value on <th> ── -->
  <table>
    <tr><th scope="invalid-scope">Bad Scope</th><td>Data</td></tr>
  </table>

  <!-- ── scrollable-region-focusable: scrollable div not keyboard reachable ── -->
  <div style="overflow:auto; height:50px; width:150px;">
    <p>Line 1</p><p>Line 2</p><p>Line 3</p><p>Line 4</p><p>Line 5</p>
  </div>

  <!-- ── select-name: <select> without an associated label ── -->
  <select id="no-select-label"><option>Option</option></select>

  <!-- ── server-side-image-map: <img ismap> ── -->
  <img src="mapimg.png" ismap alt="server map">

  <!-- ── summary-name: <summary> with no accessible text ── -->
  <details><summary></summary>Details content</details>

  <!-- ── svg-img-alt: <svg role=img> without title or aria-label ── -->
  <svg role="img" width="50" height="50"><rect width="50" height="50"/></svg>

  <!-- ── tabindex: positive tabindex value ── -->
  <div tabindex="5">High tabindex element</div>

  <!-- ── table-duplicate-name: <caption> text equals summary attribute ── -->
  <table summary="Table Summary">
    <caption>Table Summary</caption>
    <tr><td>Data</td></tr>
  </table>

  <!-- ── table-fake-caption: first row spans all columns and acts as caption ── -->
  <table>
    <tr><td colspan="3"><strong>Fake Caption Row</strong></td></tr>
    <tr><td>Col 1</td><td>Col 2</td><td>Col 3</td></tr>
    <tr><td>Data A</td><td>Data B</td><td>Data C</td></tr>
  </table>

  <!-- ── td-headers-attr: headers attribute references a nonexistent ID ── -->
  <table>
    <tr><th id="realhdr">Real Header</th></tr>
    <tr><td headers="realhdr nonexistent-id">Data</td></tr>
  </table>

  <!-- ── th-has-data-cells: <th> with no associated data cells ── -->
  <table>
    <tr><th>Lonely Header</th></tr>
  </table>

  <!-- ── td-has-header (experimental): complex data table (3×3) with no headers ── -->
  <table>
    <tr><td>A1</td><td>B1</td><td>C1</td></tr>
    <tr><td>A2</td><td>B2</td><td>C2</td></tr>
    <tr><td>A3</td><td>B3</td><td>C3</td></tr>
  </table>

  <!-- ── valid-lang: invalid BCP-47 language tag on a child element ── -->
  <p lang="xx-not-valid">Text with invalid lang attribute</p>

  <!-- ── video-caption: <video> without a <track kind="captions"> ── -->
  <video width="100" height="100">
    <source src="video.mp4" type="video/mp4">
  </video>

  <!-- ═══ LANDMARK RULES ═══════════════════════════════════════════════════ -->

  <!-- ── landmark-no-duplicate-banner: two top-level <header> elements ── -->
  <header><p>Top banner 1</p></header>
  <header><p>Top banner 2</p></header>

  <!-- ── landmark-no-duplicate-contentinfo: two top-level <footer> elements ── -->
  <footer><p>Footer 1</p></footer>
  <footer><p>Footer 2</p></footer>

  <!-- ── landmark-no-duplicate-main: two <main> elements ── -->
  <!-- ── landmark-complementary-is-top-level: <aside> nested inside <main> ── -->
  <main>
    <p>Main content 1</p>
    <aside><p>Aside nested inside main</p></aside>
  </main>
  <main><p>Main content 2</p></main>

  <!-- ── landmark-banner-is-top-level: role=banner nested inside role=navigation ── -->
  <div role="navigation">
    <div role="banner"><p>Banner inside navigation</p></div>
  </div>

  <!-- ── landmark-contentinfo-is-top-level: role=contentinfo nested inside role=navigation ── -->
  <div role="navigation">
    <div role="contentinfo"><p>Footer inside navigation</p></div>
  </div>

  <!-- ── landmark-main-is-top-level: role=main nested inside role=navigation ── -->
  <div role="navigation">
    <div role="main"><p>Main inside navigation</p></div>
  </div>

  <!-- ── landmark-unique: two <nav> landmarks share the same accessible name ── -->
  <nav aria-label="Shared Navigation"><a href="#">Link 1</a></nav>
  <nav aria-label="Shared Navigation"><a href="#">Link 2</a></nav>

</body>
</html>`;

// ─── HTTP helper ─────────────────────────────────────────────────────────────
function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const opts = {
      hostname: 'localhost',
      port:     PORT,
      path,
      method:   'POST',
      headers: {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
    };
    const req = http.request(opts, (res) => {
      let raw = '';
      res.on('data', chunk => (raw += chunk));
      res.on('end', () => {
        try { resolve(JSON.parse(raw)); }
        catch (e) { reject(new Error(`JSON parse failed: ${raw}`)); }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

// ─── Main ────────────────────────────────────────────────────────────────────
async function runSelfTest() {
  const LINE = '─'.repeat(72);
  const BOLD = '═'.repeat(72);

  console.log(BOLD);
  console.log('  AXE-CORE RULE COVERAGE SELF-TEST');
  console.log(`  API endpoint : http://localhost:${PORT}/analyze-accessibility`);
  console.log(`  Total rules  : ${ALL_RULES.length}`);
  console.log(BOLD);
  console.log();

  let response;
  try {
    console.log('Sending comprehensive bad-HTML fixture to the API...\n');
    response = await post('/analyze-accessibility', { html: BAD_HTML, timeout: 60000 });
  } catch (err) {
    console.error('ERROR: Could not reach the API —', err.message);
    console.error('Make sure the server is running:  node server.js');
    process.exit(1);
  }

  if (response.error) {
    console.error('API ERROR:', response.error);
    console.error('Message  :', response.message);
    process.exit(1);
  }

  const results     = response.results ?? [];
  const observedIds = new Set(results.map(r => r.ruleId));

  const failed      = results.filter(r => r.status === 'fail');
  const incomplete  = results.filter(r => r.status === 'incomplete');
  const passed      = results.filter(r => r.status === 'pass');
  const notObserved = ALL_RULES.filter(id => !observedIds.has(id));

  // ── Violations ──────────────────────────────────────────────────────────
  console.log(LINE);
  console.log(`VIOLATIONS DETECTED  (${failed.length})`);
  console.log(LINE);
  for (const r of failed) {
    const tag = r.impact ? `[${r.impact.toUpperCase()}]`.padEnd(12) : '            ';
    console.log(`  FAIL  ${tag} ${r.ruleId}`);
    console.log(`              ${r.reason}`);
  }
  console.log();

  // ── Incomplete / review ─────────────────────────────────────────────────
  if (incomplete.length > 0) {
    console.log(LINE);
    console.log(`INCOMPLETE / NEEDS MANUAL REVIEW  (${incomplete.length})`);
    console.log(LINE);
    for (const r of incomplete) {
      console.log(`  INCOMPLETE   ${r.ruleId}`);
    }
    console.log();
  }

  // ── Passed ──────────────────────────────────────────────────────────────
  console.log(LINE);
  console.log(`PASSED  (${passed.length})`);
  console.log(LINE);
  for (const r of passed) {
    console.log(`  PASS         ${r.ruleId}`);
  }
  console.log();

  // ── Not observed ────────────────────────────────────────────────────────
  if (notObserved.length > 0) {
    const ruleMap = Object.fromEntries(axe.getRules().map(r => [r.ruleId, r]));

    const classify = (id) => {
      if (UNREACHABLE.deprecated.has(id)) return 'deprecated — skipped by axe-core';
      if (UNREACHABLE.wcagAaa.has(id))    return 'WCAG AAA (wcag2aaa) — not in API runOnly';
      if (UNREACHABLE.wcag22.has(id))     return 'WCAG 2.2 (wcag22aa) — not in API runOnly';
      const tags = ruleMap[id]?.tags ?? [];
      if (tags.includes('experimental'))  return 'experimental — inapplicable to this fixture';
      return 'inapplicable to this fixture';
    };

    const byReason = {};
    for (const id of notObserved) {
      const reason = classify(id);
      (byReason[reason] ??= []).push(id);
    }

    console.log(LINE);
    console.log(`NOT OBSERVED  (${notObserved.length})`);
    console.log(LINE);
    for (const [reason, ids] of Object.entries(byReason)) {
      console.log(`  Reason: ${reason}`);
      for (const id of ids) {
        console.log(`    --  ${id}`);
      }
      console.log();
    }
  }

  // ── Summary ─────────────────────────────────────────────────────────────
  const covered = ALL_RULES.length - notObserved.length;
  const pct     = ((covered / ALL_RULES.length) * 100).toFixed(1);

  const maxReachable = ALL_RULES.length
    - UNREACHABLE.deprecated.size
    - UNREACHABLE.wcagAaa.size
    - UNREACHABLE.wcag22.size;
  const pctReachable = ((covered / maxReachable) * 100).toFixed(1);

  console.log(BOLD);
  console.log('  COVERAGE SUMMARY');
  console.log(BOLD);
  console.log(`  Rules observed      : ${covered} / ${ALL_RULES.length}  (${pct}% of all rules)`);
  console.log(`  Reachable coverage  : ${covered} / ${maxReachable}  (${pctReachable}% excluding deprecated/AAA/2.2)`);
  console.log(`  Violations          : ${failed.length}`);
  console.log(`  Passed              : ${passed.length}`);
  console.log(`  Incomplete/review   : ${incomplete.length}`);
  console.log(`  Not observed        : ${notObserved.length}`);
  console.log(BOLD);
}

runSelfTest();
