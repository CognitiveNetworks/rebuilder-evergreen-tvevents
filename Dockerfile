# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for confluent-kafka (librdkafka) and asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        librdkafka-dev \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
COPY src/ ./src/

# Install rebuilder-redis-module first (internal dependency), then main package
COPY output/rebuilder-redis-module /tmp/rebuilder-redis-module
RUN pip install --no-cache-dir /tmp/rebuilder-redis-module && \
    pip install --no-cache-dir . && \
    rm -rf /tmp/rebuilder-redis-module

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home appuser
USER appuser

EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "tvevents.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
