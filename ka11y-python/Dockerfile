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

# Copy only dependency manifests first. `package-mode = false` means none of the
# install/download steps below need the application source, so copying the source
# later keeps these expensive layers cached across code-only changes.
COPY pyproject.toml poetry.lock ./

RUN pip install --no-cache-dir "poetry==2.3.2"
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/root/.cache/pypoetry

# Japanese NLP support (sudachipy + sudachidict + spaCy ja_core_news_lg).
# Toggle off at build time for a smaller EN-only image:
#   docker build --build-arg INSTALL_JAPANESE=0 .
#
# spaCy resolves model URLs through raw.githubusercontent.com, which DNS-flakes
# mid-build the same way the NLTK mirror does. Same defence: retry up to 5
# times with linear backoff, then assert the model loads so a truly-down
# network fails the build loudly instead of shipping a half-populated image.
ARG INSTALL_JAPANESE=1
RUN if [ "$INSTALL_JAPANESE" = "1" ]; then \
        poetry install --only main -E japanese && \
        for attempt in 1 2 3 4 5; do \
            python -m spacy download ja_core_news_lg && break; \
            echo "[spacy] ja_core_news_lg download attempt $attempt failed; retrying in $((attempt * 10))s..."; \
            sleep $((attempt * 10)); \
        done && \
        python -c "import spacy; spacy.load('ja_core_news_lg')"; \
    else \
        poetry install --only main; \
    fi

# English spaCy model (~12MB) — loaded by sensory_auditor + quality_engine
# regardless of the Japanese toggle; without it English falls back to regex/NLTK.
# Same retry guard as the JA model above (same flaky upstream host).
RUN for attempt in 1 2 3 4 5; do \
        python -m spacy download en_core_web_sm && break; \
        echo "[spacy] en_core_web_sm download attempt $attempt failed; retrying in $((attempt * 10))s..."; \
        sleep $((attempt * 10)); \
    done; \
    python -c "import spacy; spacy.load('en_core_web_sm')"

# Pre-download NLTK corpora used by media quality_engine so EC2/air-gapped
# runs don't stall on first request.
#
# The NLTK source (raw.githubusercontent.com) intermittently fails DNS / rate-
# limits mid-download. Without a guard, the downloader drops into an interactive
# "Retry? [n/y/e]" prompt that EOFs in a non-TTY build and aborts. So: feed
# </dev/null (prompt fails fast instead of hanging), retry the whole set up to 5
# times with linear backoff (already-fetched packages are skipped on re-run),
# then assert all four corpora are present so a truly-down network still fails
# the build loudly rather than shipping a half-populated image.
RUN for attempt in 1 2 3 4 5; do \
        python -m nltk.downloader -d /usr/share/nltk_data \
            punkt punkt_tab averaged_perceptron_tagger_eng stopwords </dev/null \
        && break; \
        echo "[nltk] download attempt $attempt failed; retrying in $((attempt * 10))s..."; \
        sleep $((attempt * 10)); \
    done; \
    python -c "import nltk; nltk.data.path.insert(0, '/usr/share/nltk_data'); \
[nltk.data.find(p) for p in ['tokenizers/punkt', 'tokenizers/punkt_tab', \
'taggers/averaged_perceptron_tagger_eng', 'corpora/stopwords']]"
ENV NLTK_DATA=/usr/share/nltk_data

# Install Playwright's Chromium browser + all system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    playwright install chromium --with-deps

# Application source + i18n bundles come last: a code-only change rebuilds only
# these cheap layers, not the dependency/model/browser layers above.
COPY ka11y/ ./ka11y/
COPY i18n/   ./i18n/

# Pre-create the logs directory so it exists in the image layer.
# The python_logs Docker volume is mounted over this path at runtime;
# if the volume is not configured the directory still exists and logs work.
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]
