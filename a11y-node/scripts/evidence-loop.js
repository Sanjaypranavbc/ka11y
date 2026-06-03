#!/usr/bin/env node
'use strict';

const assert = require('assert/strict');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');

const puppeteer = require('puppeteer');

const appConfig = require('../src/config/app.config');
const { _loadCheckDefinitions } = require('../src/custom-checks/index');
const { mapCustomResultsFlat, mapResultsFlat } = require('../src/utils/axeResultMapper');
const characterKeyShortcutsCheck = require('../src/custom-checks/character-key-shortcuts.check');
const htmlParsingCheck = require('../src/custom-checks/html-parsing.check');

const execFileAsync = promisify(execFile);

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const NODE_DIR = path.resolve(__dirname, '..');
const PYTHON_DIR = path.join(REPO_ROOT, 'a11y-python');
const FRONTEND_DIR = path.join(REPO_ROOT, 'a11y-frontend-sdk');
const OUTPUT_DIR = path.join(NODE_DIR, 'logs');
const REPORT_PATH = path.join(OUTPUT_DIR, 'evidence-report.md');
const RAW_REPORT_PATH = path.join(OUTPUT_DIR, 'evidence-report.json');
const AXE_PATH = path.join(NODE_DIR, 'node_modules', 'axe-core', 'axe.min.js');
const FIXTURE_DIR = path.join(NODE_DIR, 'tests', 'fixtures', 'custom-checks');
const MAX_ATTEMPTS = parseInt(process.env.A11Y_EVIDENCE_MAX_ATTEMPTS || '3', 10);
const REQUESTED_FRONTEND_PREVIEW_PORT = process.env.A11Y_FRONTEND_PREVIEW_PORT
  ? parseInt(process.env.A11Y_FRONTEND_PREVIEW_PORT, 10)
  : null;

const FRONTEND_FIXTURE = {
  job_id: 'evidence-job',
  status: 'completed',
  url: 'https://evidence.local/proof',
  current_stage: null,
  warnings: [],
  stages: [{
    name: 'axe_core',
    status: 'completed',
    started_at: '2026-03-25T00:00:00.000Z',
    completed_at: '2026-03-25T00:00:01.000Z',
    findings_count: 3,
  }],
  result: {
    url: 'https://evidence.local/proof',
    generated_at: '2026-03-25T00:00:02.000Z',
    warnings: [],
    violations: [
      {
        source: 'axe',
        rule_id: 'landmark-complementary-is-top-level',
        wcag_sc: 'best-practice',
        criterion_name: 'Complementary Landmark at Top Level',
        level: null,
        severity: 'medium',
        reason: 'The complementary landmark is contained in another landmark.',
        suggested_fix: 'Move <aside> elements to be siblings of <main> at the top level of the page.',
        help_url: 'https://dequeuniversity.com/rules/axe/4.11/landmark-complementary-is-top-level',
        element: { html: '<aside>Related links</aside>' },
      },
      {
        source: 'axe',
        rule_id: 'color-contrast-enhanced',
        wcag_sc: '1.4.6',
        criterion_name: 'Contrast (Enhanced)',
        level: 'AAA',
        severity: 'high',
        reason: 'Text has insufficient contrast.',
        suggested_fix: 'Ensure text contrast meets enhanced thresholds.',
        help_url: 'https://dequeuniversity.com/rules/axe/4.11/color-contrast-enhanced',
        element: { html: '<p style="color:#666">Low contrast sample</p>' },
      },
    ],
    needs_review: [
      {
        source: 'custom',
        rule_id: 'custom-character-key-shortcuts',
        wcag_sc: null,
        criterion_name: null,
        level: null,
        severity: 'medium',
        reason: 'Synthetic unmapped item to prove fallback rendering.',
        suggested_fix: null,
        help_url: null,
        element: { html: '' },
      },
    ],
    passes: [
      {
        source: 'axe',
        rule_id: 'duplicate-id',
        wcag_sc: '4.1.1',
        criterion_name: 'Parsing',
        level: 'A',
        reason: 'No duplicate id attributes found.',
      },
      {
        source: 'custom',
        rule_id: 'custom-unmapped-pass',
        wcag_sc: null,
        criterion_name: null,
        level: null,
        reason: 'Synthetic unmapped pass to prove fallback rendering.',
      },
    ],
    contrast_report: null,
  },
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runCommand(label, file, args, cwd, timeoutMs = 10 * 60 * 1000) {
  try {
    const { stdout, stderr } = await execFileAsync(file, args, {
      cwd,
      env: process.env,
      encoding: 'utf8',
      timeout: timeoutMs,
      maxBuffer: 20 * 1024 * 1024,
    });
    return {
      label,
      ok: true,
      exitCode: 0,
      stdout,
      stderr,
      summary: summarizeCommandOutput(label, stdout, stderr),
    };
  } catch (error) {
    const stdout = error.stdout || '';
    const stderr = error.stderr || '';
    return {
      label,
      ok: false,
      exitCode: typeof error.code === 'number' ? error.code : 1,
      stdout,
      stderr,
      error: error.message,
      summary: summarizeCommandOutput(label, stdout, stderr) || error.message,
    };
  }
}

function summarizeCommandOutput(label, stdout, stderr) {
  const combined = [stdout, stderr].filter(Boolean).join('\n');
  if (!combined.trim()) return `${label}: no output`;

  const lines = combined.trim().split('\n').map((line) => line.trim()).filter(Boolean);

  if (label === 'node-tests') {
    const passLine = lines.find((line) => /\bTest Suites:\b/.test(line) || /\bPASS\b/.test(line));
    const testLine = lines.find((line) => /\bTests:\b/.test(line));
    return [passLine, testLine].filter(Boolean).join(' | ') || lines.slice(-4).join(' | ');
  }

  if (label === 'python-tests') {
    const summaryLine = lines.find((line) => /\bpassed\b/.test(line) || /\bfailed\b/.test(line) || /\berror\b/i.test(line));
    return summaryLine || lines.slice(-4).join(' | ');
  }

  if (label === 'frontend-lint') {
    return lines.slice(-3).join(' | ');
  }

  if (label === 'frontend-build') {
    const builtLine = lines.find((line) => /\bbuilt in\b/.test(line));
    const warningLine = lines.find((line) => /\bSome chunks are larger than\b/.test(line));
    return [builtLine, warningLine].filter(Boolean).join(' | ') || lines.slice(-5).join(' | ');
  }

  return lines.slice(-5).join(' | ');
}

async function waitForHttp(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const ok = await new Promise((resolve) => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 500);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(1500, () => {
        req.destroy();
        resolve(false);
      });
    });

    if (ok) return;
    await sleep(250);
  }

  throw new Error(`Timed out waiting for ${url}`);
}

async function getAvailablePort(preferredPort = null) {
  const tryListen = (port) => new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', (error) => {
      server.close();
      reject(error);
    });
    server.listen(port, '127.0.0.1', () => {
      const address = server.address();
      const boundPort = typeof address === 'object' && address ? address.port : port;
      server.close((closeError) => {
        if (closeError) reject(closeError);
        else resolve(boundPort);
      });
    });
  });

  if (preferredPort) return tryListen(preferredPort);
  return tryListen(0);
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.killed) return;
  await new Promise((resolve) => {
    child.once('exit', () => resolve());
    child.kill('SIGTERM');
    setTimeout(() => {
      if (child.exitCode === null) child.kill('SIGKILL');
      resolve();
    }, 3000);
  });
}

function startFrontendPreview(port) {
  const child = spawn(
    'npm',
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(port), '--strictPort'],
    {
      cwd: FRONTEND_DIR,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );

  let logs = '';
  const capture = (chunk) => {
    logs += chunk.toString();
    if (logs.length > 12000) logs = logs.slice(-12000);
  };

  child.stdout.on('data', capture);
  child.stderr.on('data', capture);

  return { child, getLogs: () => logs.trim() };
}

function makeHtml(body, extraHead = '') {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>a11y evidence</title>
    ${extraHead}
  </head>
  <body>
    ${body}
  </body>
</html>`;
}

async function withTestPage(browser, html, fn) {
  const page = await browser.newPage();
  try {
    await page.setContent(html, { waitUntil: 'domcontentloaded' });
    return await fn(page);
  } finally {
    await page.close();
  }
}

async function runAxeRule(browser, ruleId, html) {
  return withTestPage(browser, html, async (page) => {
    await page.addScriptTag({ path: AXE_PATH });
    const axeResults = await page.evaluate((targetRuleId) => {
      return new Promise((resolve, reject) => {
        // eslint-disable-next-line no-undef
        axe.run(document, { runOnly: { type: 'rule', values: [targetRuleId] } }, (err, results) => {
          if (err) reject(err);
          else resolve(results);
        });
      });
    }, ruleId);
    return mapResultsFlat(axeResults, `https://evidence.local/${ruleId}`);
  });
}

async function runCustomCheck(browser, check, html) {
  return withTestPage(browser, html, async (page) => {
    const result = await check.run(page);
    return mapCustomResultsFlat([result], 'https://evidence.local/custom');
  });
}

function recordAssertion(collection, name, fn, dataFactory = null) {
  try {
    fn();
    collection.push({
      name,
      ok: true,
      detail: dataFactory ? dataFactory() : 'ok',
    });
  } catch (error) {
    collection.push({
      name,
      ok: false,
      detail: error.message,
    });
  }
}

async function runNodeEvidence(browser) {
  const assertions = [];

  const landmarkFindings = await runAxeRule(
    browser,
    'landmark-complementary-is-top-level',
    makeHtml(`
      <nav>
        <div role="complementary">Related links</div>
      </nav>
    `)
  );
  const landmarkFinding = landmarkFindings.find((finding) => finding.rule_id === 'landmark-complementary-is-top-level');

  recordAssertion(assertions, 'axe best-practice rule is emitted', () => {
    assert.ok(landmarkFinding, 'Expected landmark-complementary-is-top-level finding');
    assert.equal(landmarkFinding.status, 'fail');
    assert.equal(landmarkFinding.wcag_sc, 'best-practice');
    assert.equal(landmarkFinding.criterion_name, 'Complementary Landmark at Top Level');
    assert.match(landmarkFinding.suggested_fix || '', /Move <aside> elements/i);
  }, () => landmarkFinding);

  const contrastFailFindings = await runAxeRule(
    browser,
    'color-contrast-enhanced',
    makeHtml(`
      <p style="color:#666;background:#fff;font-size:16px;">
        Enhanced contrast failure sample.
      </p>
    `)
  );
  const contrastFail = contrastFailFindings.find((finding) => finding.rule_id === 'color-contrast-enhanced');

  recordAssertion(assertions, 'AAA 1.4.6 failure maps to WCAG metadata', () => {
    assert.ok(contrastFail, 'Expected color-contrast-enhanced failure');
    assert.equal(contrastFail.status, 'fail');
    assert.equal(contrastFail.wcag_sc, '1.4.6');
    assert.equal(contrastFail.criterion_name, 'Contrast (Enhanced)');
    assert.equal(contrastFail.level, 'AAA');
  }, () => contrastFail);

  const contrastPassFindings = await runAxeRule(
    browser,
    'color-contrast-enhanced',
    makeHtml(`
      <p style="color:#222;background:#fff;font-size:16px;">
        Enhanced contrast pass sample.
      </p>
    `)
  );
  const contrastPass = contrastPassFindings.find((finding) => finding.rule_id === 'color-contrast-enhanced');

  recordAssertion(assertions, 'AAA 1.4.6 pass is reflected in flat results', () => {
    assert.ok(contrastPass, 'Expected color-contrast-enhanced pass');
    assert.equal(contrastPass.status, 'pass');
    assert.equal(contrastPass.wcag_sc, '1.4.6');
    assert.equal(contrastPass.criterion_name, 'Contrast (Enhanced)');
    assert.equal(contrastPass.level, 'AAA');
  }, () => contrastPass);

  const htmlParsingFailFindings = await runCustomCheck(
    browser,
    htmlParsingCheck,
    makeHtml(`
      <main>
        <div id="dup">One</div>
        <div id="dup">Two</div>
      </main>
    `)
  );
  const htmlParsingFail = htmlParsingFailFindings.find((finding) => finding.rule_id === 'custom-html-parsing');

  recordAssertion(assertions, 'custom HTML parsing failure is emitted', () => {
    assert.ok(htmlParsingFail, 'Expected custom-html-parsing failure');
    assert.equal(htmlParsingFail.status, 'fail');
    assert.equal(htmlParsingFail.wcag_sc, '4.1.1');
    assert.equal(htmlParsingFail.criterion_name, 'Parsing');
    assert.match(htmlParsingFail.reason, /duplicate id attribute/i);
  }, () => htmlParsingFail);

  const htmlParsingPassFindings = await runCustomCheck(
    browser,
    htmlParsingCheck,
    makeHtml(`
      <main>
        <div id="alpha">One</div>
        <div id="beta">Two</div>
      </main>
    `)
  );
  const htmlParsingPass = htmlParsingPassFindings.find((finding) => finding.rule_id === 'custom-html-parsing');

  recordAssertion(assertions, 'custom HTML parsing pass is reflected', () => {
    assert.ok(htmlParsingPass, 'Expected custom-html-parsing pass');
    assert.equal(htmlParsingPass.status, 'pass');
    assert.equal(htmlParsingPass.wcag_sc, '4.1.1');
  }, () => htmlParsingPass);

  const shortcutFailFindings = await runCustomCheck(
    browser,
    characterKeyShortcutsCheck,
    makeHtml(`
      <button accesskey="s">Save</button>
      <button onkeydown="if (event.key === 'x') window.__a11yEvidence = true;">Shortcut</button>
    `)
  );
  const shortcutFail = shortcutFailFindings.find((finding) => finding.rule_id === 'custom-character-key-shortcuts');

  recordAssertion(assertions, 'character key shortcuts issue is surfaced as needs_review', () => {
    assert.ok(shortcutFail, 'Expected custom-character-key-shortcuts finding');
    assert.equal(shortcutFail.status, 'needs_review');
    assert.equal(shortcutFail.wcag_sc, '2.1.4');
    assert.equal(shortcutFail.criterion_name, 'Character Key Shortcuts');
    assert.match(shortcutFail.reason, /accesskey/i);
  }, () => shortcutFail);

  const shortcutPassFindings = await runCustomCheck(
    browser,
    characterKeyShortcutsCheck,
    makeHtml(`
      <button onkeydown="if (event.ctrlKey && event.key === 's') window.__a11yEvidence = true;">Save</button>
    `)
  );
  const shortcutPass = shortcutPassFindings.find((finding) => finding.rule_id === 'custom-character-key-shortcuts');

  recordAssertion(assertions, 'character key shortcuts pass is reflected', () => {
    assert.ok(shortcutPass, 'Expected custom-character-key-shortcuts pass');
    assert.equal(shortcutPass.status, 'pass');
    assert.equal(shortcutPass.wcag_sc, '2.1.4');
  }, () => shortcutPass);

  const discoveredChecks = _loadCheckDefinitions(FIXTURE_DIR);
  const pluginCheck = discoveredChecks.find((entry) => entry.ruleId === 'plugin-smoke-check');

  recordAssertion(assertions, 'custom checks are plugin-discoverable from new files', () => {
    assert.ok(pluginCheck, 'Expected fixture plugin to be discovered');
    assert.equal(pluginCheck.mode, 'static');
  }, () => ({
    ruleId: pluginCheck && pluginCheck.ruleId,
    mode: pluginCheck && pluginCheck.mode,
  }));

  return assertions;
}

async function installFrontendMocks(page) {
  await page.evaluateOnNewDocument((fixture) => {
    class FakeEventSource {
      constructor() {
        this.listeners = Object.create(null);
        setTimeout(() => {
          this._emit('job_state', {
            job_id: fixture.job_id,
            current_stage: 'axe_core',
            stages: [{
              name: 'axe_core',
              status: 'running',
              started_at: '2026-03-25T00:00:00.000Z',
            }],
          });
          this._emit('stage_complete', {
            stage_name: 'axe_core',
            completed_at: '2026-03-25T00:00:01.000Z',
            findings_count: 3,
          });
          this._emit('job_complete', { job_id: fixture.job_id });
        }, 100);
      }

      addEventListener(type, callback) {
        if (!this.listeners[type]) this.listeners[type] = [];
        this.listeners[type].push(callback);
      }

      close() {}

      _emit(type, payload) {
        const callbacks = this.listeners[type] || [];
        const event = { data: JSON.stringify(payload) };
        callbacks.forEach((callback) => callback(event));
      }
    }

    window.EventSource = FakeEventSource;
  }, FRONTEND_FIXTURE);

  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const url = request.url();

    if (request.method() === 'POST' && /\/api\/v1\/combined\/?$/.test(url)) {
      request.respond({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: FRONTEND_FIXTURE.job_id }),
      });
      return;
    }

    if (request.method() === 'GET' && new RegExp(`/api/v1/combined/${FRONTEND_FIXTURE.job_id}$`).test(url)) {
      request.respond({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FRONTEND_FIXTURE),
      });
      return;
    }

    request.continue();
  });
}

async function clickButtonByText(page, text) {
  const clicked = await page.$$eval('button', (buttons, label) => {
    const target = buttons.find((button) => {
      const value = (button.textContent || '').replace(/\s+/g, ' ').trim();
      return value.includes(label);
    });
    if (!target) return false;
    target.click();
    return true;
  }, text);

  assert.equal(clicked, true, `Could not find button containing "${text}"`);
}

async function runFrontendEvidence(browser, previewUrl) {
  const assertions = [];

  const desktopPage = await browser.newPage();
  try {
    await desktopPage.setViewport({ width: 1440, height: 960 });
    await installFrontendMocks(desktopPage);
    await desktopPage.goto(previewUrl, { waitUntil: 'networkidle2' });

    const toggleSelector = 'button[aria-label*="mode"]';
    await desktopPage.waitForSelector(toggleSelector);

    const beforeToggle = await desktopPage.evaluate(() => document.documentElement.classList.contains('dark'));
    await desktopPage.click(toggleSelector);
    await desktopPage.waitForFunction((expected) => document.documentElement.classList.contains('dark') !== expected, {}, beforeToggle);
    const afterToggle = await desktopPage.evaluate(() => document.documentElement.classList.contains('dark'));

    recordAssertion(assertions, 'dark mode has a dedicated header toggle button', () => {
      assert.notEqual(beforeToggle, afterToggle);
    }, () => ({ beforeToggle, afterToggle }));

    await desktopPage.type('#audit-url', FRONTEND_FIXTURE.url);
    await clickButtonByText(desktopPage, 'Run Audit');
    await desktopPage.waitForFunction(
      (expectedUrl) => document.body.innerText.includes(expectedUrl),
      {},
      FRONTEND_FIXTURE.url
    );

    await clickButtonByText(desktopPage, 'Violations');
    await desktopPage.waitForFunction(
      () => document.body.innerText.includes('Complementary Landmark at Top Level'),
      {}
    );

    const violationTable = await desktopPage.evaluate(() => {
      const table = document.querySelector('table');
      return {
        text: table ? table.innerText : '',
        summary: document.body.innerText,
      };
    });

    recordAssertion(assertions, 'violations table shows populated SC and criterion values', () => {
      assert.match(violationTable.text, /best-practice/);
      assert.match(violationTable.text, /Complementary Landmark at Top Level/);
      assert.match(violationTable.text, /1\.4\.6/);
      assert.match(violationTable.text, /Contrast \(Enhanced\)/);
    }, () => violationTable);

    await clickButtonByText(desktopPage, 'high');
    await desktopPage.waitForFunction(
      () => document.body.innerText.includes('Showing 1 of 1 violations'),
      {}
    );
    const filteredSummary = await desktopPage.$eval('body', (body) => body.innerText);

    recordAssertion(assertions, 'violations filters are dynamic and reduce the visible result set', () => {
      assert.match(filteredSummary, /Showing 1 of 1 violations/);
    }, () => ({ filteredSummary }));

    await clickButtonByText(desktopPage, 'Needs Review');
    await desktopPage.waitForFunction(
      () => document.body.innerText.includes('Synthetic unmapped item to prove fallback rendering.'),
      {}
    );
    const needsReviewText = await desktopPage.$eval('body', (body) => body.innerText);

    recordAssertion(assertions, 'needs-review table replaces empty values with fallback labels', () => {
      assert.match(needsReviewText, /unmapped/i);
      assert.match(needsReviewText, /Unmapped criterion/);
    }, () => ({ needsReviewText }));

    await clickButtonByText(desktopPage, 'Passes');
    await desktopPage.waitForFunction(
      () => document.body.innerText.includes('Synthetic unmapped pass to prove fallback rendering.'),
      {}
    );
    const passesText = await desktopPage.$eval('body', (body) => body.innerText);

    recordAssertion(assertions, 'passes table renders fallback labels instead of blank cells', () => {
      assert.match(passesText, /unmapped/i);
      assert.match(passesText, /Unmapped criterion/);
    }, () => ({ passesText }));
  } finally {
    await desktopPage.close();
  }

  const mobilePage = await browser.newPage();
  try {
    await mobilePage.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await installFrontendMocks(mobilePage);
    await mobilePage.goto(previewUrl, { waitUntil: 'networkidle2' });
    await mobilePage.click('button[aria-label="Open navigation"]');
    await mobilePage.waitForFunction(() => {
      const sidebar = document.querySelector('aside[aria-label="Audit controls"]');
      if (!sidebar) return false;
      return sidebar.getBoundingClientRect().left > -20;
    });

    const sidebarState = await mobilePage.evaluate(() => {
      const sidebar = document.querySelector('aside[aria-label="Audit controls"]');
      const firstNavButton = document.querySelector('nav[aria-label="Main navigation"] button');
      if (!sidebar || !firstNavButton) return null;
      const rect = sidebar.getBoundingClientRect();
      return {
        left: rect.left,
        width: rect.width,
        cursor: window.getComputedStyle(firstNavButton).cursor,
      };
    });

    recordAssertion(assertions, 'mobile sidebar opens and left-nav cursor stays pointer', () => {
      assert.ok(sidebarState, 'Expected mobile sidebar state');
      assert.ok(sidebarState.width > 0, 'Expected visible sidebar width');
      assert.ok(sidebarState.left > -20, `Expected sidebar to be visible, got left=${sidebarState.left}`);
      assert.equal(sidebarState.cursor, 'pointer');
    }, () => sidebarState);
  } finally {
    await mobilePage.close();
  }

  return assertions;
}

async function runEvidenceAttempt(attempt) {
  const commands = [];
  commands.push(await runCommand('node-tests', 'npm', ['test'], NODE_DIR));
  commands.push(await runCommand('python-tests', 'python', ['-m', 'pytest'], PYTHON_DIR));
  commands.push(await runCommand('frontend-lint', 'npm', ['run', 'lint'], FRONTEND_DIR));
  commands.push(await runCommand('frontend-build', 'npm', ['run', 'build'], FRONTEND_DIR));

  const previewPort = await getAvailablePort(REQUESTED_FRONTEND_PREVIEW_PORT);
  const previewUrl = `http://127.0.0.1:${previewPort}/`;
  const preview = startFrontendPreview(previewPort);
  let browser = null;

  try {
    await waitForHttp(previewUrl);

    browser = await puppeteer.launch({
      headless: appConfig.browser.headless,
      executablePath: appConfig.browser.executablePath,
      args: appConfig.browser.args,
    });

    const nodeAssertions = await runNodeEvidence(browser);
    const frontendAssertions = await runFrontendEvidence(browser, previewUrl);
    const commandFailures = commands.filter((entry) => !entry.ok).length;
    const assertionFailures = [...nodeAssertions, ...frontendAssertions].filter((entry) => !entry.ok).length;

    return {
      attempt,
      commands,
      nodeAssertions,
      frontendAssertions,
      bugCount: commandFailures + assertionFailures,
      previewLogs: preview.getLogs(),
    };
  } finally {
    if (browser) await browser.close();
    await stopChild(preview.child);
  }
}

function renderTable(rows) {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const separator = `| ${headers.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${headers.map((header) => String(row[header])).join(' | ')} |`);
  return [
    `| ${headers.join(' | ')} |`,
    separator,
    ...body,
  ].join('\n');
}

function renderAssertions(assertions) {
  return assertions.map((item) => ({
    Check: item.name,
    Status: item.ok ? 'PASS' : 'BUG',
    Detail: typeof item.detail === 'string'
      ? item.detail.replace(/\n+/g, ' ').slice(0, 180)
      : JSON.stringify(item.detail).slice(0, 180),
  }));
}

function writeReport(finalResult, attempts) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const lines = [];
  lines.push('# a11y Evidence Report');
  lines.push('');
  lines.push(`Generated: ${new Date().toISOString()}`);
  lines.push(`Loop attempts: ${attempts.length}`);
  lines.push(`Converged bug count: ${finalResult.bugCount}`);
  lines.push('');
  lines.push('## Validation Summary');
  lines.push('');
  lines.push(renderTable(finalResult.commands.map((command) => ({
    Command: command.label,
    Status: command.ok ? 'PASS' : 'FAIL',
    Exit: command.exitCode,
    Summary: command.summary.replace(/\|/g, '\\|'),
  }))));
  lines.push('');
  lines.push('## Node Evidence');
  lines.push('');
  lines.push(renderTable(renderAssertions(finalResult.nodeAssertions).map((row) => ({
    ...row,
    Detail: row.Detail.replace(/\|/g, '\\|'),
  }))));
  lines.push('');
  lines.push('## Frontend Evidence');
  lines.push('');
  lines.push(renderTable(renderAssertions(finalResult.frontendAssertions).map((row) => ({
    ...row,
    Detail: row.Detail.replace(/\|/g, '\\|'),
  }))));
  lines.push('');
  lines.push('## Loop History');
  lines.push('');
  lines.push(renderTable(attempts.map((attempt) => ({
    Attempt: attempt.attempt,
    Bugs: attempt.bugCount,
    Commands: attempt.commands.filter((entry) => !entry.ok).length,
    Assertions: [...attempt.nodeAssertions, ...attempt.frontendAssertions].filter((entry) => !entry.ok).length,
  }))));
  lines.push('');

  if (finalResult.previewLogs) {
    lines.push('## Frontend Preview Logs');
    lines.push('');
    lines.push('```text');
    lines.push(finalResult.previewLogs);
    lines.push('```');
    lines.push('');
  }

  fs.writeFileSync(REPORT_PATH, `${lines.join('\n')}\n`, 'utf8');
  fs.writeFileSync(RAW_REPORT_PATH, JSON.stringify({ attempts }, null, 2), 'utf8');
}

async function main() {
  const attempts = [];
  let finalResult = null;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const result = await runEvidenceAttempt(attempt);
    attempts.push(result);
    finalResult = result;

    if (result.bugCount === 0) break;
  }

  writeReport(finalResult, attempts);

  if (!finalResult || finalResult.bugCount !== 0) {
    console.error(`Evidence loop finished with ${finalResult ? finalResult.bugCount : 'unknown'} bug(s).`);
    console.error(`See ${REPORT_PATH}`);
    process.exitCode = 1;
    return;
  }

  console.log(`Evidence loop passed with 0 bugs after ${attempts.length} attempt(s).`);
  console.log(`Report: ${REPORT_PATH}`);
}

main().catch((error) => {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.writeFileSync(REPORT_PATH, `# a11y Evidence Report\n\nExecution failed: ${error.stack || error.message}\n`, 'utf8');
  console.error(error);
  process.exitCode = 1;
});
