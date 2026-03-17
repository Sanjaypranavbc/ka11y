FROM python:3.13-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
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

COPY pyproject.toml ./
COPY ka11y/ ./ka11y/

RUN pip install --no-cache-dir --upgrade poetry
RUN poetry install

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]