#!/usr/bin/env bash
set -euo pipefail

# Source environment validation
source /app/environment-check.sh

# Configure AWS region
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"

# Initialize blacklist cache from RDS at startup
echo "[entrypoint] Initializing blacklist cache from RDS..."
python -c "
from tvevents.infrastructure.database import RdsClient
from tvevents.infrastructure.cache import BlacklistCache
rds = RdsClient()
cache = BlacklistCache()
ids = rds.fetch_blacklisted_channel_ids()
if ids:
    cache.store(ids)
    print(f'[entrypoint] Cached {len(ids)} blacklisted channel IDs')
else:
    print('[entrypoint] WARNING: No blacklisted channel IDs fetched from RDS')
" || echo "[entrypoint] WARNING: Cache initialization failed — will retry on first request"

# Launch ASGI server with conditional OTEL auto-instrumentation
if [ "${OTEL_ENABLED:-true}" = "true" ] && [ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
    echo "[entrypoint] Starting with OTEL auto-instrumentation"
    exec opentelemetry-instrument \
        --service_name "${OTEL_SERVICE_NAME:-tvevents-k8s}" \
        uvicorn tvevents.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "${UVICORN_WORKERS:-4}" \
        --log-level "${LOG_LEVEL:-info}"
else
    echo "[entrypoint] Starting without OTEL auto-instrumentation"
    exec uvicorn tvevents.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "${UVICORN_WORKERS:-4}" \
        --log-level "${LOG_LEVEL:-info}"
fi
