# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.lock ./
# The lock pins every version to what the test suite ran against.
RUN pip install --no-cache-dir --prefix=/install -c requirements.lock .

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    shared-mime-info \
    fonts-liberation2 \
    fonts-urw-base35 \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fontconfig \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Export fonts: every family the font picker offers, or a metric-compatible
# substitute, so a PDF exported here matches one exported on a desktop.
# Before this, a missing family fell back to whatever WeasyPrint found.
# Ahead of the application code, so code changes do not redownload them.
COPY fonts /tmp/font-setup/fonts
COPY scripts/install-fonts.sh /tmp/font-setup/scripts/install-fonts.sh
RUN sh /tmp/font-setup/scripts/install-fonts.sh && rm -rf /tmp/font-setup

# Copy application code
COPY . .

# The database and uploads/ both resolve from here (see app/paths.py), so this must
# match the volume mount in docker-compose.yml. Unset, they land in /app and are
# discarded when the container is recreated.
ENV TYPECAST_DATA_DIR=/app/data

# Create directories for mounted volumes
RUN mkdir -p /app/data/uploads /app/profiles

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
