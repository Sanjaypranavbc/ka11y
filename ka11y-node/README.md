# WCAG Accessibility API

A Node.js REST API that analyzes raw HTML for accessibility issues using [axe-core](https://github.com/dequelabs/axe-core) and [Puppeteer](https://pptr.dev/). It maps each result back to its WCAG Success Criterion and returns structured JSON that is easy to integrate into CI pipelines or developer tooling.

---

## Features

- Analyzes any HTML string for WCAG 2.0 / 2.1 Level A & AA violations, passes, and incomplete checks
- Filters results by a specific WCAG Success Criterion (e.g. `1.1.1`, `4.1.2`)
- Returns rule ID, description, impact, status, reason, and a documentation link for every rule
- Interactive API documentation via Swagger UI at `/api-docs`
- Structured file-based logging organized by date (`logs/YYYY/MM/DD/`)

---

## Project Structure

```
wcag/
├── server.js                        # Express app entry point
├── selftest.js                      # Axe-core rule coverage self-test
├── package.json
├── .env                             # Environment variable overrides
├── Dockerfile
├── src/
│   ├── config/
│   │   ├── app.config.js            # Centralised configuration
│   │   └── swagger.config.js        # OpenAPI / Swagger setup
│   ├── controllers/
│   │   ├── accessibility.controller.js
│   │   ├── health.controller.js
│   │   ├── rules.controller.js
│   │   └── rulesGuide.controller.js
│   ├── services/
│   │   ├── accessibility.service.js # Puppeteer + axe-core orchestration
│   │   └── rules.service.js
│   └── utils/
│       ├── axeResultMapper.js       # Maps axe results to WCAG criteria
│       ├── logger.js                # File + console logger
│       ├── rulesGuide.js
│       └── wcagCriteriaNames.js
└── logs/                            # Auto-created at runtime
    └── YYYY/
        └── MM/
            └── DD/
                ├── info.log
                ├── warn.log
                ├── error.log
                └── debug.log
```

---

## Requirements

- Node.js >= 18
- npm >= 9

> Puppeteer downloads a bundled Chromium automatically during `npm install`. No separate browser installation is needed.

---

## Installation

```bash
# Clone or copy the project
cd wcag

# Install dependencies (also downloads Chromium for Puppeteer)
npm install
```

---

## Configuration

Copy `.env` and adjust values as needed:

```env
# TCP port the server listens on
PORT=3000

# Maximum request body size
BODY_LIMIT=10mb

# Timeout for a single axe-core analysis (milliseconds)
AXE_TIMEOUT_MS=30000
```

All variables have defaults and the server runs without a `.env` file.

---

## Running the Server

### Development (auto-restart on file changes)

```bash
npm run dev
```

### Production

```bash
npm start
```

The server starts on `http://localhost:3000` (or the port set in `.env`).

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Server health check |
| GET | `/rules` | List all axe-core rules (optional `?tags=` filter) |
| GET | `/rules-guide` | WCAG success criteria reference guide |
| GET | `/rules-guide/:ruleId` | Detail for a single rule |
| POST | `/analyze-accessibility` | Analyze HTML for accessibility issues |
| GET | `/api-docs` | Interactive Swagger UI |

### POST `/analyze-accessibility`

**Request body:**

```json
{
  "html": "<img src='logo.png'>",
  "successCriteriaId": "1.1.1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `html` | string | Yes | Raw HTML to analyze. Use single quotes for HTML attributes to avoid breaking the JSON string. |
| `successCriteriaId` | string | No | Filter results to a single WCAG SC (e.g. `"1.1.1"`). Omit to return all rules. |

**Response (200):**

```json
{
  "results": [
    {
      "ruleId": "image-alt",
      "description": "Ensure <img> elements have alternative text",
      "impact": "critical",
      "status": "fail",
      "reason": "Element does not have an alt attribute",
      "helpUrl": "https://dequeuniversity.com/rules/axe/4.11/image-alt"
    }
  ]
}
```

| Field | Values |
|-------|--------|
| `status` | `fail` \| `pass` \| `incomplete` |
| `impact` | `critical` \| `serious` \| `moderate` \| `minor` \| `null` |

**Error responses:**

| Code | Reason |
|------|--------|
| 400 | Missing or non-string `html` field, or malformed JSON body |
| 500 | Browser launch failure or internal analysis error |

### Example — curl

```bash
# Analyze an image missing alt text, filtered to SC 1.1.1
curl -X POST http://localhost:3000/analyze-accessibility \
  -H "Content-Type: application/json" \
  -d '{"html": "<img src=\"logo.png\">", "successCriteriaId": "1.1.1"}'

# Full page analysis (no filter)
curl -X POST http://localhost:3000/analyze-accessibility \
  -H "Content-Type: application/json" \
  -d '{"html": "<!DOCTYPE html><html lang=\"en\"><head><title>Test</title></head><body><h1>Hello</h1></body></html>"}'
```

---

## Logging

Logs are written to both the console (coloured) and date-stamped files under `logs/`.

**Directory layout:**

```
logs/
└── 2026/
    └── 03/
        └── 12/
            ├── info.log    # Informational messages
            ├── warn.log    # Warnings (e.g. 4xx requests, malformed input)
            ├── error.log   # Errors (e.g. 5xx, analysis failures)
            └── debug.log   # Browser console errors, detailed trace
```

Each line in a log file follows the format:

```
[LEVEL] [2026-03-12T10:45:00.000Z] message
```

---

## Self-Test

`selftest.js` sends a comprehensive "intentionally broken" HTML fixture to the running API and reports which axe-core rules were detected, passed, or not observed.

```bash
# Server must be running first
npm start

# In a second terminal
npm run selftest

# Target a different port
node selftest.js --port 4000
```

The output shows violations, incomplete checks, passed rules, not-observed rules (with reasons), and a coverage percentage.

---

## Docker

### Build

```bash
docker build -t wcag-api .
```

### Run

```bash
docker run -p 3000:3000 wcag-api
```

### Run with custom environment

```bash
docker run -p 4000:3000 \
  -e PORT=3000 \
  -e AXE_TIMEOUT_MS=60000 \
  wcag-api
```

The Docker image uses a non-root user and installs all Chromium system dependencies required by Puppeteer.

---

## WCAG Coverage

The API runs axe-core with the following rule tags:

- `wcag2a` — WCAG 2.0 Level A
- `wcag2aa` — WCAG 2.0 Level AA
- `wcag21a` — WCAG 2.1 Level A
- `wcag21aa` — WCAG 2.1 Level AA
- `best-practice` — Axe-core best-practice rules

WCAG 2.2 (`wcag22aa`) and AAA-only rules are not included in the default configuration.

---

## CORS

By default the API only accepts requests from `http://localhost` (any port). To allow other origins, update `cors.origin` in `src/config/app.config.js`.
