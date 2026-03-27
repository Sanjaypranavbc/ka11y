# =============================================================================
# ka11y-node — Puppeteer + axe-core accessibility engine
# =============================================================================

# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM node:20-slim AS deps

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

WORKDIR /app

COPY package*.json ./

RUN echo "==> [deps 2/2] Installing production Node dependencies..." && \
    npm install --omit=dev && \
    echo "==> [deps 2/2] Node dependencies installed ($(du -sh node_modules | cut -f1) on disk)"


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM node:20-slim AS runtime

LABEL org.opencontainers.image.title="ka11y-node"
LABEL org.opencontainers.image.description="Puppeteer + axe-core WCAG accessibility engine"

RUN echo "==> [1/4] Installing system Chromium..." && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        chromium \
        ca-certificates \
        curl \
        fonts-liberation \
        fonts-noto-color-emoji \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnss3 \
        libxss1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && echo "==> [1/4] Chromium installed: $(chromium --version)"

WORKDIR /app

RUN echo "==> [2/4] Copying node_modules from deps stage..."
COPY --from=deps /app/node_modules ./node_modules
RUN echo "==> [2/4] node_modules copied ($(du -sh node_modules | cut -f1))"

RUN echo "==> [3/4] Copying application source..."
COPY package*.json ./
COPY server.js     ./
COPY src/          ./src/
COPY i18n/         ./i18n/
RUN echo "==> [3/4] Source copied"

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV NODE_ENV=production
RUN echo "==> [4/4] Puppeteer configured to use system Chromium at $(which chromium)"

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:3000/api/v1/health || exit 1

CMD ["node", "server.js"]