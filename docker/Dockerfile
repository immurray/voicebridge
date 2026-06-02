# VoiceBridge Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Build arg for cache busting
ARG GIT_SHA=dev
ENV BUILD_COMMIT=${GIT_SHA}

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

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
