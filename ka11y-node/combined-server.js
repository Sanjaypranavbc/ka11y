'use strict';

const AccessibilityService = require('./src/services/accessibility.service');
const Config = require('./src/config/app.config');
const Logger = require('./src/utils/logger');
const app = require('./server');

// Initialize services to check the puppeteer/axe installation
const testService = new AccessibilityService(
  require('puppeteer'),
  require('path').resolve(__dirname, 'node_modules/axe-core/axe.min.js'),
  Logger,
  Config
);

app.post('/api/ka11y/combined', async (req, res) => {
  const { url } = req.query;
  if (!url) {
    return res.status(400).json({ error: 'url parameter is required' });
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(url);
  } catch (err) {
    return res.status(400).json({ error: 'url must be a valid fully-qualified HTTP/HTTPS URL' });
  }

  if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
    return res.status(400).json({ error: 'url protocol must be http or https' });
  }

  // 1. Run Node accessibility checks (Puppeteer + axe-core + custom checks)
  const nodePromise = testService.analyseUrl(url)
    .then(results => ({ status: 'success', data: results }))
    .catch(err => ({ status: 'error', message: err.message }));

  // 2. Run Python accessibility checks
  const pythonBaseUrl = process.env.PYTHON_BASE_URL || 'http://localhost:8000';
  const pythonPromise = fetch(`${pythonBaseUrl}/api/v1/crawl`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, max_depth: 0 })
  })
    .then(async response => {
      if (!response.ok) {
        throw new Error(`Python service returned status ${response.status}`);
      }
      const data = await response.json();
      return { status: 'success', data };
    })
    .catch(err => ({ status: 'error', message: err.message }));

  // 3. Await both in parallel
  const [nodeRes, pythonRes] = await Promise.all([nodePromise, pythonPromise]);

  // 4. Extract total and critical issues, and warnings
  let totalIssues = 0;
  let criticalIssues = 0;
  let warningIssues = 0;

  if (nodeRes.status === 'success' && Array.isArray(nodeRes.data)) {
    for (const group of nodeRes.data) {
      if (group && Array.isArray(group.rules)) {
        for (const rule of group.rules) {
          if (rule.status === 'fail') {
            totalIssues += 1;
            if (rule.impact === 'critical') {
              criticalIssues += 1;
            }
          }
        }
      }
    }
  }

  if (pythonRes.status === 'success' && pythonRes.data) {
    // Basic heuristics to count Python issues if any (Python schema is crawl-based, findings details might vary)
    const elements = pythonRes.data.elements || [];
    for (const el of elements) {
      if (el.classification === 'failed' || el.status === 'FAILED') {
        totalIssues += 1;
        criticalIssues += 1; // Default to critical for failed checks
      } else if (el.status === 'NEEDS_REVIEW') {
        warningIssues += 1;
      }
    }
  }

  const responsePayload = {
    url,
    node_result: nodeRes.status === 'success' ? nodeRes.data : { error: nodeRes.message },
    python_result: pythonRes.status === 'success' ? pythonRes.data : { error: pythonRes.message },
    combined_summary: {
      total_issues: totalIssues,
      critical: criticalIssues,
      warnings: warningIssues
    }
  };

  res.json(responsePayload);
});

module.exports = app;
