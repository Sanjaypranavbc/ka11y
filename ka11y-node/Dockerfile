# syntax=docker/dockerfile:1.7
# =============================================================================
# ka11y-node — Puppeteer + axe-core accessibility engine
# =============================================================================

# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM node:20-slim AS deps

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

WORKDIR /app

COPY package*.json ./

# Cache mount for npm so repeat builds reuse the package tarball cache.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev --prefer-offline --no-audit --no-fund


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM node:20-slim AS runtime

LABEL org.opencontainers.image.title="ka11y-node"
LABEL org.opencontainers.image.description="Puppeteer + axe-core WCAG accessibility engine"

# System Chromium + minimal runtime libs. Cache mounts keep apt downloads
# across rebuilds, so this layer stays fast even if invalidated.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
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
        libasound2

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules

# Source layer — changes often, kept last so dep/system layers stay cached.
COPY package*.json ./
COPY server.js     ./
COPY src/          ./src/
COPY i18n/         ./i18n/

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV NODE_ENV=production

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://localhost:3000/api/v1/health || exit 1

CMD ["node", "server.js"]
