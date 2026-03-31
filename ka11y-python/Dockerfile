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
RUN poetry install --only main

# Install Playwright's Chromium browser + all system dependencies
RUN poetry run playwright install chromium --with-deps

# Pre-create the logs directory so it exists in the image layer.
# The python_logs Docker volume is mounted over this path at runtime;
# if the volume is not configured the directory still exists and logs work.
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]