# =============================================================================
# ka11y-frontend — React (Vite) → nginx reverse proxy
# Stage 1: build the React app
# Stage 2: serve with nginx + proxy /api/ → python:8000
# =============================================================================

# ── Stage 1: Node builder ─────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# ── [1/4] Install dependencies ────────────────────────────────────────────────
RUN echo "==> [1/4] Copying package manifests..."
COPY package.json package-lock.json* ./
RUN echo "==> [1/4] Installing npm dependencies..." && \
    npm ci --prefer-offline && \
    echo "==> [1/4] Dependencies installed"

# ── [2/4] Copy source and build ───────────────────────────────────────────────
RUN echo "==> [2/4] Copying application source..."
COPY . .
RUN echo "==> [2/4] Source copied"

RUN echo "==> [3/4] Building React app (vite build)..." && \
    npm run build && \
    echo "==> [3/4] Build complete ($(du -sh dist | cut -f1))"


# ── Stage 2: nginx runtime ────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

RUN echo "==> [4/4] Copying build artefacts and nginx config..."
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN echo "==> [4/4] nginx image ready"

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ > /dev/null || exit 1