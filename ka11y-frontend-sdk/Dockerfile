# syntax=docker/dockerfile:1.7
# =============================================================================
# ka11y-frontend — React (Vite) → nginx reverse proxy
# Stage 1: build the React app
# Stage 2: serve with nginx + proxy /api/ → python:8000
# =============================================================================

# ── Stage 1: Node builder ─────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# Dependency layer — cached unless package*.json changes.
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

# Source layer — kept last so npm ci stays cached across source edits.
COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build


# ── Stage 2: nginx runtime ────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/ > /dev/null || exit 1
