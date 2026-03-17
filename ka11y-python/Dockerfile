# =============================================================================
# ka11y-python — FastAPI + Playwright accessibility auditor
# Python 3.13 · Poetry · Playwright Chromium · PyTorch CPU
# =============================================================================

# ── Stage 1: system base + Poetry ────────────────────────────────────────────
FROM python:3.13-slim AS base

LABEL org.opencontainers.image.title="ka11y-python"
LABEL org.opencontainers.image.description="FastAPI accessibility auditor — Python 3.13 + Playwright + Poetry"

# Python runtime flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Poetry config
ENV POETRY_VERSION=2.1.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    POETRY_INSTALLER_PARALLEL=true

ENV PATH="$POETRY_HOME/bin:/app/.venv/bin:$PATH"

WORKDIR /app

# ── [1/8] Install system packages ────────────────────────────────────────────
RUN echo "==> [1/8] Updating apt package index..." && \
    apt-get update -qq && \
    echo "==> [1/8] Installing system packages (build tools, OpenCV, font libs)..." && \
    apt-get install -y --no-install-recommends \
        # --- essential build tools ---
        build-essential \
        curl \
        git \
        ca-certificates \
        # --- OpenCV / EasyOCR runtime libs ---
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
        libgomp1 \
        # --- Pillow / image processing ---
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        # --- fonts for Playwright rendering ---
        fonts-liberation \
        fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && echo "==> [1/8] System packages installed"


# ── Stage 2: Poetry + Python deps installer ───────────────────────────────────
FROM base AS builder

# ── [2/8] Install Poetry ──────────────────────────────────────────────────────
RUN echo "==> [2/8] Downloading and installing Poetry ${POETRY_VERSION}..." && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry --version && \
    echo "==> [2/8] Poetry installed at $(which poetry)"

# ── [3/8] Copy dependency manifests only (cache layer) ───────────────────────
RUN echo "==> [3/8] Copying pyproject.toml and poetry.lock..."
COPY pyproject.toml poetry.lock* ./
RUN echo "==> [3/8] Manifests copied"

# ── [4/8] Install Python dependencies ────────────────────────────────────────
# torch is pulled from pytorch-cpu source (defined in pyproject.toml)
RUN echo "==> [4/8] Installing Python dependencies via Poetry..." && \
    echo "    NOTE: PyTorch CPU + transformers + easyocr = ~3 GB — please wait" && \
    poetry config package-mode false && \
    poetry install --no-root --only main 2>&1 | \
        while IFS= read -r line; do \
            echo "  poetry: $line"; \
        done && \
    echo "==> [4/8] Python dependencies installed (venv: $(du -sh .venv | cut -f1))"


# ── Stage 3: runtime image ────────────────────────────────────────────────────
FROM base AS runtime

# Copy the virtual environment from builder
RUN echo "==> [5/8] Copying Python virtual environment from builder stage..."
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /opt/poetry /opt/poetry
RUN echo "==> [5/8] Virtual environment copied ($(du -sh .venv | cut -f1))"

# ── [6/8] Install Playwright Chromium + its system dependencies ───────────────
# --with-deps installs all required OS-level packages automatically
RUN echo "==> [6/8] Installing Playwright Chromium browser + system dependencies..." && \
    playwright install chromium --with-deps 2>&1 | \
        while IFS= read -r line; do \
            echo "  playwright: $line"; \
        done && \
    echo "==> [6/8] Playwright Chromium installed"

# ── [7/8] Copy application source ─────────────────────────────────────────────
RUN echo "==> [7/8] Copying application source..."
COPY ka11y/ ./ka11y/
RUN echo "==> [7/8] Application source copied"

# ── [8/8] Final setup ─────────────────────────────────────────────────────────
RUN echo "==> [8/8] Creating output directories and verifying environment..." && \
    mkdir -p /app/crawled_images /app/logs && \
    python -c "import fastapi, playwright, uvicorn; print('  FastAPI:', fastapi.__version__)" && \
    echo "==> [8/8] Environment verified — image is ready"

# Environment defaults (overridable via docker-compose / -e flags)
ENV NODE_BASE_URL="http://localhost:3000" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/pipeline/ -X POST \
        -H "Content-Type: application/json" \
        -d '{"url":"http://example.com","run_ocr":false,"run_image_audit":false,"run_form_audit":false,"run_label_in_name_audit":false,"run_pause_stop_hide_audit":false,"run_target_size_audit":false}' \
        -o /dev/null --max-time 10 || \
    curl -f http://localhost:8000/docs -o /dev/null --max-time 5 || exit 1

CMD ["uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]