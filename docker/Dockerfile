# VoiceBridge Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Build args
ARG GIT_SHA=dev
ARG BUILD_TS=0
ENV BUILD_COMMIT=${GIT_SHA}

# Unique label forces fresh image digest on every build
LABEL build_ts=${BUILD_TS}

# System deps: ffmpeg (PCM→MP3 conversion for Piper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Piper TTS binary (static, ~5MB, local offline fallback)
RUN curl -sL https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
    | tar xz -C /tmp && mv /tmp/piper/piper /usr/local/bin/ && rm -rf /tmp/piper

# Model download directory (persist via volume mount)
RUN mkdir -p /data/piper-models

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY app/ ./app/
COPY static/ ./static/

# Inject build commit into HTML for cache busting
RUN sed -i "s/__BUILD_COMMIT__/${GIT_SHA}/g" static/index.html

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
