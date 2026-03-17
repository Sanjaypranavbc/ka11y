# =============================================================================
# ka11y-node — Puppeteer + axe-core accessibility engine
# =============================================================================

# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM node:20-slim AS deps

# Skip Puppeteer's bundled Chrome download — we use system Chromium instead
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

WORKDIR /app

RUN echo "==> [deps 1/2] Copying package manifests..."
COPY package*.json ./

RUN echo "==> [deps 2/2] Installing production Node dependencies (npm ci)..." && \
    npm ci --omit=dev --prefer-offline 2>&1 | \
        while IFS= read -r line; do echo "  npm: $line"; done && \
    echo "==> [deps 2/2] Node dependencies installed ($(du -sh node_modules | cut -f1) on disk)"


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM node:20-slim AS runtime

LABEL org.opencontainers.image.title="ka11y-node"
LABEL org.opencontainers.image.description="Puppeteer + axe-core WCAG accessibility engine"

# ── [1/5] Install system Chromium (apt resolves all deps correctly) ───────────
RUN echo "==> [1/5] Installing system Chromium..." && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        chromium \
        ca-certificates \
        curl \
        fonts-liberation \
        fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && echo "==> [1/5] Chromium installed: $(chromium --version)"

WORKDIR /app

# ── [2/5] Copy pre-built node_modules from deps stage ────────────────────────
RUN echo "==> [2/5] Copying node_modules from deps stage..."
COPY --from=deps /app/node_modules ./node_modules
RUN echo "==> [2/5] node_modules copied ($(du -sh node_modules | cut -f1))"

# ── [3/5] Copy application source ────────────────────────────────────────────
RUN echo "==> [3/5] Copying application source..."
COPY package*.json ./
COPY server.js     ./
COPY src/          ./src/
RUN echo "==> [3/5] Source copied"

# ── [4/5] Puppeteer — point to system Chromium, skip bundled download ─────────
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV NODE_ENV=production
RUN echo "==> [4/5] Puppeteer configured to use system Chromium at $(which chromium)"

# ── [5/5] Non-root security user ─────────────────────────────────────────────
RUN echo "==> [5/5] Creating non-root user 'appuser'..." && \
    groupadd -r appuser && \
    useradd -r -g appuser -G audio,video appuser && \
    chown -R appuser:appuser /app && \
    echo "==> [5/5] User 'appuser' created"

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:3000/api/v1/health || exit 1

CMD ["node", "server.js"]