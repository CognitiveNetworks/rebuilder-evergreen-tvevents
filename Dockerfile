FROM python:3.12-slim AS base

LABEL maintainer="tvevents-k8s"
LABEL service="tvevents-k8s"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from compiled requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install OTEL auto-instrumentation packages
RUN opentelemetry-bootstrap --action=install

# Copy application source
COPY src/ /app/src/
COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/environment-check.sh /app/environment-check.sh

RUN chmod +x /app/entrypoint.sh /app/environment-check.sh

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
RUN chown -R appuser:appuser /app && \
    mkdir -p /tmp && chown appuser:appuser /tmp

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
