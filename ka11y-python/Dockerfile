FROM python:3.13-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
    # faster-whisper audio decoding
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

RUN pip install --no-cache-dir --upgrade poetry

# Japanese NLP support (sudachipy + sudachidict + spaCy ja_core_news_lg).
# Toggle off at build time for a smaller EN-only image:
#   docker build --build-arg INSTALL_JAPANESE=0 .
ARG INSTALL_JAPANESE=1
RUN if [ "$INSTALL_JAPANESE" = "1" ]; then \
        poetry install --only main -E japanese && \
        poetry run python -m spacy download ja_core_news_lg; \
    else \
        poetry install --only main; \
    fi

# Pre-download NLTK corpora used by media quality_engine so EC2/air-gapped
# runs don't stall on first request.
RUN poetry run python -m nltk.downloader -d /usr/share/nltk_data \
        punkt punkt_tab averaged_perceptron_tagger_eng stopwords
ENV NLTK_DATA=/usr/share/nltk_data

# Pre-download faster-whisper (base, int8, CPU) so first media audit does not
# pull ~150MB at request time. Override at build time with WHISPER_MODEL_SIZE=tiny
# for a smaller image.
ARG WHISPER_MODEL_SIZE=base
ENV WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE}
RUN poetry run python -c "from faster_whisper import WhisperModel; \
        WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"

# Install Playwright's Chromium browser + all system dependencies
RUN poetry run playwright install chromium --with-deps

# Pre-create the logs directory so it exists in the image layer.
# The python_logs Docker volume is mounted over this path at runtime;
# if the volume is not configured the directory still exists and logs work.
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]