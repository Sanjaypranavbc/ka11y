'use strict';

const swaggerJsdoc = require('swagger-jsdoc');
const path = require('path');

const options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'WCAG Accessibility API',
      version: '1.0.0',
      description: 'A Node.js Express API to evaluate HTML accessibility using axe-core and Puppeteer',
    },
    servers: [
      {
        url: 'http://localhost:3000',
        description: 'Local server',
      },
    ],
  },
  // Path to the API docs
  apis: [path.resolve(__dirname, '../controllers/*.js')],
};

const swaggerSpec = swaggerJsdoc(options);

module.exports = swaggerSpec;
