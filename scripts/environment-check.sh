#!/usr/bin/env bash
set -euo pipefail

# Environment variable validation for tvevents-k8s
# Groups: RDS, Kafka, Application, OTEL

ERRORS=0

check_var() {
    local var_name="$1"
    local group="$2"
    if [ -z "${!var_name:-}" ]; then
        echo "[env-check] ERROR: ${group} — ${var_name} is not set"
        ERRORS=$((ERRORS + 1))
    fi
}

# Skip validation in test containers
if [ "${TEST_CONTAINER:-false}" = "true" ]; then
    echo "[env-check] TEST_CONTAINER mode — skipping environment validation"
    return 0 2>/dev/null || exit 0
fi

echo "[env-check] Validating environment variables..."

# RDS Group
check_var "RDS_HOST" "RDS"
check_var "RDS_DB" "RDS"
check_var "RDS_USER" "RDS"
check_var "RDS_PASS" "RDS"
check_var "RDS_PORT" "RDS"

# Kafka Group
check_var "KAFKA_BOOTSTRAP_SERVERS" "Kafka"

# Application Group
check_var "T1_SALT" "Application"
check_var "ENV" "Application"

# OTEL Group (warnings only — optional)
if [ "${OTEL_ENABLED:-true}" = "true" ]; then
    if [ -z "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
        echo "[env-check] WARNING: OTEL — OTEL_EXPORTER_OTLP_ENDPOINT is not set (OTEL will be disabled)"
    fi
fi

if [ "$ERRORS" -gt 0 ]; then
    echo "[env-check] FAILED: ${ERRORS} required variable(s) missing"
    exit 1
fi

echo "[env-check] All required environment variables are set"
