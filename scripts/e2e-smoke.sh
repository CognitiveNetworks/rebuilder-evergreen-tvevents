#!/usr/bin/env bash
set -euo pipefail

# End-to-end smoke test for tvevents-k8s
# Usage: ./scripts/e2e-smoke.sh [BASE_URL]
#
# Requires: curl, jq

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }

check() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "$actual" = "$expected" ]; then
        green "  PASS: $name"
        PASS=$((PASS + 1))
    else
        red "  FAIL: $name (expected=$expected, actual=$actual)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== tvevents-k8s E2E Smoke Test ==="
echo "Target: $BASE_URL"
echo

# --- Health Endpoints ---
echo "1. GET /status"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/status")
check "HTTP 200" "200" "$STATUS"

echo "2. GET /health"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/health")
check "HTTP 200" "200" "$STATUS"

# --- Ops Endpoints ---
echo "3. GET /ops/status"
BODY=$(curl -s "$BASE_URL/ops/status")
STATUS=$(echo "$BODY" | jq -r '.service')
check "service=tvevents-k8s" "tvevents-k8s" "$STATUS"

echo "4. GET /ops/metrics"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/ops/metrics")
check "HTTP 200" "200" "$HTTP"

echo "5. GET /ops/config"
BODY=$(curl -s "$BASE_URL/ops/config")
SVC=$(echo "$BODY" | jq -r '.service_name')
check "service_name=tvevents-k8s" "tvevents-k8s" "$SVC"
# Verify no secrets
HAS_SALT=$(echo "$BODY" | jq 'has("t1_salt")')
check "no t1_salt in config" "false" "$HAS_SALT"

echo "6. GET /ops/errors"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/ops/errors")
check "HTTP 200" "200" "$HTTP"

echo "7. GET /ops/circuits"
BODY=$(curl -s "$BASE_URL/ops/circuits")
RDS_STATE=$(echo "$BODY" | jq -r '.circuits.rds')
check "rds circuit=closed" "closed" "$RDS_STATE"

echo "8. POST /ops/loglevel"
BODY=$(curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"level":"DEBUG"}' "$BASE_URL/ops/loglevel")
CURRENT=$(echo "$BODY" | jq -r '.current')
check "loglevel changed to DEBUG" "DEBUG" "$CURRENT"
# Reset
curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"level":"INFO"}' "$BASE_URL/ops/loglevel" > /dev/null

# --- Ingestion (requires valid hash) ---
echo "9. POST / with missing payload"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' \
    -d '{}' "$BASE_URL/?tvid=smoke&event_type=ACR_TUNER_DATA")
check "missing payload returns 400" "400" "$HTTP"

# --- OpenAPI Spec ---
echo "10. GET /openapi.json"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/openapi.json")
check "HTTP 200" "200" "$HTTP"

# --- Summary ---
echo
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    red "SMOKE TEST FAILED"
    exit 1
else
    green "SMOKE TEST PASSED"
    exit 0
fi
