# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

# System libs needed for OpenCV / Playwright / ffmpeg / image decoding.
# Use a cache mount so repeat builds don't re-download .deb packages.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ffmpeg \
        libxcb1 \
        libxext6 \
        libxrender1 \
        libx11-6 \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libjpeg-dev \
        libpng-dev \
        zlib1g-dev

WORKDIR /app

# ── Dependency layer (cached unless poetry.lock / pyproject.toml change) ──────
# Source code is intentionally NOT copied here so the heavy install / model
# download layers below stay cached across source edits.
COPY pyproject.toml poetry.lock ./

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install "poetry==2.3.2"

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/root/.cache/pypoetry \
    PATH=/app/.venv/bin:$PATH

# Japanese NLP support (sudachipy + sudachidict + spaCy ja_core_news_lg).
# Toggle off at build time for a smaller EN-only image:
#   docker build --build-arg INSTALL_JAPANESE=0 .
ARG INSTALL_JAPANESE=1
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    --mount=type=cache,target=/root/.cache/pip \
    if [ "$INSTALL_JAPANESE" = "1" ]; then \
        poetry install --only main -E japanese && \
        /app/.venv/bin/python -m spacy download ja_core_news_lg; \
    else \
        poetry install --only main; \
    fi

# Pre-download NLTK corpora used by media quality_engine so EC2/air-gapped
# runs don't stall on first request.
RUN /app/.venv/bin/python -m nltk.downloader -d /usr/share/nltk_data \
        punkt punkt_tab averaged_perceptron_tagger_eng stopwords
ENV NLTK_DATA=/usr/share/nltk_data

# Pre-download faster-whisper (base, int8, CPU) so first media audit does not
# pull ~150MB at request time. Override at build time with WHISPER_MODEL_SIZE=tiny
# for a smaller image.
ARG WHISPER_MODEL_SIZE=base
ENV WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE}
RUN /app/.venv/bin/python -c "from faster_whisper import WhisperModel; \
        WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"

# Install Playwright's Chromium browser + all system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    /app/.venv/bin/playwright install chromium --with-deps

# Pre-create the logs directory so it exists in the image layer.
# The python_logs Docker volume is mounted over this path at runtime;
# if the volume is not configured the directory still exists and logs work.
RUN mkdir -p /app/logs

# ── Source layer (changes most often — keep last so above stays cached) ──────
COPY ka11y/ ./ka11y/
COPY i18n/   ./i18n/

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]
