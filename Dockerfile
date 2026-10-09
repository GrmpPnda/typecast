# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Build backend dependencies
FROM python:3.12-slim AS backend-builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/requirements.lock ./
# [postgres] pulls in asyncpg. Without it the image cannot open a DATABASE_URL
# pointing at Postgres, which is the deployment configuration. The lock pins
# every version to what the test suite ran against.
RUN pip install --no-cache-dir --prefix=/install -c requirements.lock ".[postgres]"

# Stage 3: Runtime
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-builder /install /usr/local
COPY backend/ ./

# Built frontend served as static files
COPY --from=frontend-builder /app/dist ./static

# Data directory: uploads, plus the SQLite database when DATABASE_URL is unset.
# Mount persistent storage here (Azure Files on Container Apps).
RUN mkdir -p /data/uploads

ENV TYPECAST_DATA_DIR=/data
ENV TYPECAST_STATIC_DIR=/app/static

# The commit this image was built from, reported by /api/health.
ARG TYPECAST_VERSION=dev
ENV TYPECAST_VERSION=$TYPECAST_VERSION

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# --proxy-headers is required, not optional, behind a TLS-terminating load
# balancer. Without it every request looks like http: app/api/gdrive.py derives
# the Google OAuth redirect URI from request.url, so it would build an http://
# URI that Google rejects, and TYPECAST_FORCE_HTTPS would redirect in a loop.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
