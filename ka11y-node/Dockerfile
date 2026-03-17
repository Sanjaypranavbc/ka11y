# =============================================================================
# ka11y-node — Puppeteer + axe-core accessibility engine
# =============================================================================

# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM node:20-slim AS deps

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

# ── [1/6] System libraries required by Chromium (Puppeteer bundled) ──────────
RUN echo "==> [1/6] Updating apt package index..." && \
    apt-get update -qq && \
    echo "==> [1/6] Installing Chromium system libraries..." && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-liberation \
        fonts-noto-color-emoji \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libc6 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libexpat1 \
        libfontconfig1 \
        libgbm1 \
        libgcc1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libstdc++6 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libxrender1 \
        libxss1 \
        libxtst6 \
        lsb-release \
        wget \
        xdg-utils \
    && rm -rf /var/lib/apt/lists/* \
    && echo "==> [1/6] Chromium system libraries installed"

WORKDIR /app

# ── [2/6] Copy pre-built node_modules from deps stage ────────────────────────
RUN echo "==> [2/6] Copying node_modules from deps stage..."
COPY --from=deps /app/node_modules ./node_modules
RUN echo "==> [2/6] node_modules copied ($(du -sh node_modules | cut -f1))"

# ── [3/6] Copy application source ────────────────────────────────────────────
RUN echo "==> [3/6] Copying application source..."
COPY package*.json ./
COPY server.js     ./
COPY src/          ./src/
RUN echo "==> [3/6] Source copied"

# ── [4/6] Puppeteer — use the bundled Chromium from node_modules ─────────────
RUN echo "==> [4/6] Configuring Puppeteer (bundled Chromium)..."
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false
ENV NODE_ENV=production
RUN echo "==> [4/6] Puppeteer configured"

# ── [5/6] Non-root security user ─────────────────────────────────────────────
RUN echo "==> [5/6] Creating non-root user 'appuser'..." && \
    groupadd -r appuser && \
    useradd -r -g appuser -G audio,video appuser && \
    chown -R appuser:appuser /app && \
    echo "==> [5/6] User 'appuser' created"

USER appuser

# ── [6/6] Final configuration ─────────────────────────────────────────────────
RUN echo "==> [6/6] Final image configuration complete"

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:3000/api/v1/health || exit 1

CMD ["node", "server.js"]