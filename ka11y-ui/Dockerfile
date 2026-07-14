# =============================================================================
# ka11y-ui — Next.js accessibility audit dashboard
# =============================================================================

# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM node:20-slim AS deps

WORKDIR /app

COPY package.json package-lock.json* ./

RUN echo "==> [deps] Installing npm dependencies..." && \
    npm ci --prefer-offline && \
    echo "==> [deps] Dependencies installed"


# ── Stage 2: build ────────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN echo "==> [build] Building Next.js app..." && \
    npm run build && \
    echo "==> [build] Build complete"


# ── Stage 3: runtime ───────────────────────────────────────────────────────────
FROM node:20-slim AS runtime

LABEL org.opencontainers.image.title="ka11y-ui"
LABEL org.opencontainers.image.description="Next.js accessibility audit dashboard"

ENV NODE_ENV=production
ENV PORT=3001
ENV HOSTNAME=0.0.0.0

WORKDIR /app

RUN echo "==> [runtime] Copying standalone build output..."
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
RUN echo "==> [runtime] Standalone image ready"

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
