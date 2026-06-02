# VoiceBridge Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Build args
ARG GIT_SHA=dev
ARG BUILD_TS=0
ENV BUILD_COMMIT=${GIT_SHA}

# Unique label forces fresh image digest on every build
LABEL build_ts=${BUILD_TS}

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
