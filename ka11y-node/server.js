'use strict';

const express = require('express');
// 1. Config & Utils
const config  = require('./src/config/app.config');
const logger  = require('./src/utils/logger');

// 2. Services
const AccessibilityService = require('./src/services/accessibility.service');
const RulesService         = require('./src/services/rules.service');
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

const healthController        = new HealthController(logger);
const accessibilityController = new AccessibilityController(accessibilityService, logger);
const rulesController         = new RulesController(rulesService, logger);
const rulesGuideController    = new RulesGuideController(logger);

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
  const allowedOrigins = (process.env.ALLOWED_ORIGINS || 'http://localhost:5173,http://localhost:3000').split(',');
  const origin = req.headers.origin;
  if (origin && allowedOrigins.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  } else if (!origin) {
    res.setHeader('Access-Control-Allow-Origin', '*');
  }
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
app.post(`${API_V1}/analyse-url-flat`,      (req, res) => accessibilityController.analyseUrlFlat(req, res));
app.get( `${API_V1}/rules`,                 (req, res) => rulesController.getRules(req, res));
app.get( `${API_V1}/rules-guide`,           (req, res) => rulesGuideController.getAll(req, res));
app.get( `${API_V1}/rules-guide/:ruleId`,   (req, res) => rulesGuideController.getOne(req, res));

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
