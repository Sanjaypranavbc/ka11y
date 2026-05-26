FROM python:3.13-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
    # audio/video container decoding for media checks
    ffmpeg \
    # opencv / cv2 dependencies
    libxcb1 \
    libxext6 \
    libxrender1 \
    libx11-6 \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    # image format support
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock ./
COPY ka11y/ ./ka11y/
COPY i18n/   ./i18n/

RUN pip install --no-cache-dir "poetry==2.3.2"
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/root/.cache/pypoetry

# Japanese NLP support (sudachipy + sudachidict + spaCy ja_core_news_lg).
# Toggle off at build time for a smaller EN-only image:
#   docker build --build-arg INSTALL_JAPANESE=0 .
ARG INSTALL_JAPANESE=1
RUN if [ "$INSTALL_JAPANESE" = "1" ]; then \
        poetry install --only main -E japanese && \
        python -m spacy download ja_core_news_lg; \
    else \
        poetry install --only main; \
    fi

# English spaCy model (~12MB) — loaded by sensory_auditor + quality_engine
# regardless of the Japanese toggle; without it English falls back to regex/NLTK.
RUN python -m spacy download en_core_web_sm

# Pre-download NLTK corpora used by media quality_engine so EC2/air-gapped
# runs don't stall on first request.
RUN python -m nltk.downloader -d /usr/share/nltk_data \
        punkt punkt_tab averaged_perceptron_tagger_eng stopwords
ENV NLTK_DATA=/usr/share/nltk_data

# Install Playwright's Chromium browser + all system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    playwright install chromium --with-deps

# Pre-create the logs directory so it exists in the image layer.
# The python_logs Docker volume is mounted over this path at runtime;
# if the volume is not configured the directory still exists and logs work.
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]
