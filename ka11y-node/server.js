'use strict';

const express = require('express');
const cors    = require('cors');
const axe     = require('axe-core');

// 1. Config & Utils
const config            = require('./src/config/app.config');
const logger            = require('./src/utils/logger');
const wcagCriteriaNames = require('./src/utils/wcagCriteriaNames');

// 2. Services
const AccessibilityService = require('./src/services/accessibility.service');
const RulesService         = require('./src/services/rules.service');
const swaggerSpec          = require('./src/config/swagger.config');
const swaggerUi            = require('swagger-ui-express');

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

app.use(cors(config.cors));
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
app.get('/health',               (req, res) => healthController.getHealth(req, res));
app.get('/rules',                (req, res) => rulesController.getRules(req, res));
app.get('/rules-guide',          (req, res) => rulesGuideController.getAll(req, res));
app.get('/rules-guide/:ruleId',  (req, res) => rulesGuideController.getOne(req, res));
app.post('/analyze-accessibility', (req, res) => accessibilityController.analyze(req, res));

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
    logger.info(`  GET  ${BASE_URL}/health                  — Liveness / readiness probe`);
    logger.info(`  GET  ${BASE_URL}/rules?tags=wcag2a,...   — List axe-core rules by WCAG tag`);
    logger.info(`  GET  ${BASE_URL}/rules-guide             — Full WCAG criteria reference guide`);
    logger.info(`  GET  ${BASE_URL}/rules-guide/:ruleId     — Single WCAG criterion detail`);
    logger.info(`  POST ${BASE_URL}/analyze-accessibility   — Run axe-core audit on a URL`);
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
