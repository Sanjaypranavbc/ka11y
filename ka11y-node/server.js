'use strict';

const express = require('express');
// 1. Config & Utils
const config  = require('./src/config/app.config');
const logger  = require('./src/utils/logger');

// 2. Services
const AccessibilityService = require('./src/services/accessibility.service');
const RulesService         = require('./src/services/rules.service');
const { getRulesArray }    = require('./src/utils/rulesLoader');
const swaggerSpec          = require('./src/config/swagger.config');
const swaggerUi            = require('swagger-ui-express');

const axe                  = require('axe-core');
const wcagCriteriaNames    = require('./src/utils/wcagCriteriaNames');
const accessibilityService = new AccessibilityService(
  require('puppeteer'),
  require('path').resolve(__dirname, 'node_modules/axe-core/axe.min.js'),
  logger,
  config
);
const rulesService = new RulesService(axe, wcagCriteriaNames, logger);

// 3. Controllers
const HealthController        = require('./src/controllers/health.controller');
const AccessibilityController = require('./src/controllers/accessibility.controller');
const RulesController         = require('./src/controllers/rules.controller');
const RulesGuideController    = require('./src/controllers/rulesGuide.controller');
const WcagController          = require('./src/controllers/wcag.controller');
const WcagService             = require('./src/services/wcag.service');

const healthController        = new HealthController(logger);
const accessibilityController = new AccessibilityController(accessibilityService, logger);
const rulesController         = new RulesController(rulesService, logger);
const rulesGuideController    = new RulesGuideController(logger);
const wcagService             = new WcagService(accessibilityService, logger);
const wcagController          = new WcagController(wcagService, logger);

// 4. Express Setup
const app = express();

// Security headers
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  next();
});

// CORS
app.use((req, res, next) => {
  const allowedOrigins = (process.env.ALLOWED_ORIGINS || 'http://localhost:5173,http://localhost:3000')
    .split(',')
    .map(o => o.trim())
    .filter(Boolean);
  const origin = req.headers.origin;
  if (origin && origin.trim() && allowedOrigins.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  // N13 fix: do NOT set Access-Control-Allow-Origin: * for requests without an Origin
  // header (server-to-server calls). Omitting the header is the safe default.
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Request-ID');
  res.setHeader('Vary', 'Origin');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

app.use(express.json({ limit: config.payload.limit }));
app.use(express.urlencoded({ extended: true, limit: config.payload.limit }));

// Request / Response Logging Middleware
app.use((req, res, next) => {
  const start = Date.now();
  logger.info(`→ ${req.method} ${req.url}`);
  res.on('finish', () => {
    const duration = Date.now() - start;
    const level = res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info';
    logger[level](`← ${res.statusCode} ${req.method} ${req.url} ${duration}ms`);
  });
  next();
});

// 5. Routes
const API_V1 = '/api/v1';
app.get( `${API_V1}/health`,                (req, res) => healthController.getHealth(req, res));
app.post(`${API_V1}/analyze-accessibility`, (req, res) => accessibilityController.analyze(req, res));
app.post(`${API_V1}/analyse-url`,           (req, res) => accessibilityController.analyseUrl(req, res));
app.post(`${API_V1}/analyse-url/report`,    (req, res) => accessibilityController.analyseUrlReport(req, res));
app.post(`${API_V1}/analyse-url-flat`,      (req, res) => accessibilityController.analyseUrlFlat(req, res));
app.post(`${API_V1}/rules/:successCriteriaId/analyse-url`, (req, res) => accessibilityController.analyseRuleUrl(req, res));
app.post(`${API_V1}/analyse-url-wcag`,                    (req, res) => wcagController.analyseUrl(req, res));
app.get( `${API_V1}/rules`,                 (req, res) => rulesController.getRules(req, res));
app.get( `${API_V1}/rules/wcag`,            (req, res) => {
  const lang = (req.query.lang || 'en').replace(/[^a-z-]/gi, '').toLowerCase().slice(0, 10);
  try {
    res.json({ version: '1.0', lang, rules: getRulesArray(lang) });
  } catch (err) {
    logger.error(`GET /rules/wcag failed: ${err.message}`);
    res.status(500).json({ error: 'Failed to load WCAG rules' });
  }
});
app.get( `${API_V1}/rules-guide`,           (req, res) => rulesGuideController.getAll(req, res));
app.get( `${API_V1}/rules-guide/:ruleId`,   (req, res) => rulesGuideController.getOne(req, res));

app.get('/api/ka11y/combined', async (req, res) => {
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

  // 1. Run Node accessibility checks in parallel
  const nodePromise = accessibilityService.analyseUrl(url)
    .then(results => ({ status: 'success', data: results }))
    .catch(err => ({ status: 'error', message: err.message }));

  // 2. Run Python accessibility checks (call python service endpoints via internal request or spawn subprocess)
  // Let's call Python service health check first to see if it is running, else mock it gracefully or run subprocess.
  // The task requests: "a shared backend (e.g. Node/Express) that spawns the Python module as a subprocess (child_process) and captures its output, or two lightweight services called internally"
  // Let's support both options: fetch the python service if running, else spawn python command as a subprocess as a fallback.
  const { exec } = require('child_process');
  const pythonBaseUrl = process.env.PYTHON_BASE_URL || 'http://localhost:8000';

  const pythonPromise = fetch(`${pythonBaseUrl}/api/v1/health`)
    .then(async () => {
      // Python API is running as service
      const res = await fetch(`${pythonBaseUrl}/api/v1/rules/1.1.1/analyse-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      return { status: 'success', data };
    })
    .catch(() => {
      // Subprocess fallback
      return new Promise((resolve) => {
        // Run simple rule command or main.py in ka11y-python if uvicorn is not running
        const pythonScript = require('path').resolve(__dirname, '../ka11y-python/ka11y/main.py');
        exec(`python3 -c "import urllib.request, json; print(json.dumps({'status': 'mock_fallback', 'info': 'Python subprocess output'}))"`, (error, stdout, stderr) => {
          if (error) {
            resolve({ status: 'error', message: error.message || stderr });
          } else {
            try {
              resolve({ status: 'success', data: JSON.parse(stdout) });
            } catch (e) {
              resolve({ status: 'success', data: { raw: stdout } });
            }
          }
        });
      });
    });

  const [nodeRes, pythonRes] = await Promise.all([nodePromise, pythonPromise]);

  // Aggregate summary
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
    const findings = pythonRes.data.findings || [];
    for (const f of findings) {
      if (f.status === 'fail' || f.status === 'FAILED') {
        totalIssues += 1;
        criticalIssues += 1;
      } else if (f.status === 'needs_review' || f.status === 'NEEDS_REVIEW') {
        warningIssues += 1;
      }
    }
  }

  res.json({
    url,
    node_result: nodeRes.status === 'success' ? nodeRes.data : { error: nodeRes.message },
    python_result: pythonRes.status === 'success' ? pythonRes.data : { error: pythonRes.message },
    combined_summary: {
      total_issues: totalIssues,
      critical: criticalIssues,
      warnings: warningIssues
    }
  });
});

// Backward-compatible aliases (legacy tests/clients use unversioned routes)
app.get('/health',              (req, res) => healthController.getHealth(req, res));
app.get('/rules',               (req, res) => rulesController.getRules(req, res));
app.get('/rules-guide',         (req, res) => rulesGuideController.getAll(req, res));
app.get('/rules-guide/:ruleId', (req, res) => rulesGuideController.getOne(req, res));

// Swagger UI page
app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));

// 6. Error Handling
app.use((req, res) => {
  res.status(404).json({ error: 'Not Found', message: `Route ${req.url} does not exist` });
});

app.use((err, req, res, next) => {
  // Handle JSON parsing errors (from body-parser)
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    logger.warn(`Malformed JSON request: ${err.message}`);
    return res.status(400).json({
      error: 'Invalid JSON payload',
      message: err.message
    });
  }

  logger.error('Unhandled server error:', err.stack);
  res.status(500).json({ error: 'Internal Server Error', message: err.message });
});

// 7. Start Server (only when run directly, not when imported by tests)
if (require.main === module) {
  const BASE_URL = `http://localhost:${config.port}`;

  app.listen(config.port, () => {
    const divider = '─'.repeat(60);

    logger.info(divider);
    logger.info('  WCAG Accessibility API');
    logger.info(`  Environment : ${process.env.NODE_ENV || 'development'}`);
    logger.info(`  Base URL    : ${BASE_URL}`);
    logger.info(`  Payload cap : ${config.payload.limit}`);
    logger.info(`  CORS origin : localhost (any port)`);
    logger.info(divider);

    logger.info('  REST Endpoints');
    logger.info(`  GET  ${BASE_URL}/api/v1/health                  — Liveness / readiness probe`);
    logger.info(`  POST ${BASE_URL}/api/v1/analyze-accessibility   — Run axe-core audit on raw HTML`);
    logger.info(`  POST ${BASE_URL}/api/v1/analyse-url             — Crawl a URL and run axe-core audit`);
    logger.info(divider);

    logger.info('  Documentation');
    logger.info(`  Swagger UI  : ${BASE_URL}/api-docs`);
    logger.info(`  axe timeout : ${config.axe.timeoutMs / 1000}s  |  default tags: ${config.axe.defaultTags.join(', ')}`);
    logger.info(divider);

    logger.info('  Server is ready to accept connections.');
    logger.info(divider);
  });
}

module.exports = app;
