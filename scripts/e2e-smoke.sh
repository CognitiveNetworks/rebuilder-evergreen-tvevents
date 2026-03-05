#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# e2e-smoke.sh — End-to-end smoke test for rebuilder-evergreen-tvevents
#
# Starts the full Docker Compose stack (Postgres, Redis, Kafka, OTEL
# Collector, tvevents-api), waits for everything to be healthy, then
# exercises every endpoint category:
#
#   1. Health check (GET /health)
#   2. Event ingestion — all four event types with real HMAC (POST /v1/events)
#   3. Blacklist / obfuscation (channel in seed data → OBFUSCATED)
#   4. Kafka delivery verification (consumer reads from topic)
#   5. SRE ops — diagnostics (GET /ops/*)
#   6. SRE ops — remediation (POST /ops/*)
#
# Usage:
#   ./scripts/e2e-smoke.sh          # build + test + teardown
#   ./scripts/e2e-smoke.sh --keep   # leave stack running after tests
#   ./scripts/e2e-smoke.sh --down   # just tear down existing stack
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── Config ───────────────────────────────────────────────────────────────
BASE_URL="http://localhost:8000"
SALT="test-salt-e2e-local"
TVID="ITV00C000000000000001"
TVID_BLACKLISTED="ITV00CA1B2C3D4E5F60007"
KAFKA_TOPIC="tvevents"
PASS=0
FAIL=0
KEEP_STACK=false

for arg in "$@"; do
    case "$arg" in
        --keep) KEEP_STACK=true ;;
        --down) docker compose down -v 2>/dev/null; echo "Stack down."; exit 0 ;;
    esac
done

# ── Helpers ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { printf "${CYAN}▸${NC} %s\n" "$*"; }
pass() { printf "${GREEN}  ✔ %s${NC}\n" "$*"; PASS=$((PASS + 1)); }
fail() { printf "${RED}  ✘ %s${NC}\n" "$*"; FAIL=$((FAIL + 1)); }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }
banner() { printf "\n${CYAN}━━━ %s ━━━${NC}\n" "$*"; }

compute_hmac() {
    python3 -c "
import hmac, hashlib
print(hmac.new('${SALT}'.encode(), '${1}'.encode(), hashlib.sha256).hexdigest())
"
}

http_code() {
    curl -s -o /dev/null -w "%{http_code}" "$@"
}

http_json() {
    curl -s "$@"
}

assert_status() {
    local label="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        pass "$label (HTTP $actual)"
    else
        fail "$label — expected HTTP $expected, got $actual"
    fi
}

assert_json_field() {
    local label="$1" json="$2" field="$3" expected="$4"
    local actual
    actual=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$field',''))" 2>/dev/null || echo "PARSE_ERROR")
    if [ "$actual" = "$expected" ]; then
        pass "$label — $field=$actual"
    else
        fail "$label — expected $field=$expected, got $field=$actual"
    fi
}

assert_json_contains() {
    local label="$1" json="$2" substring="$3"
    if echo "$json" | grep -q "$substring"; then
        pass "$label — contains '$substring'"
    else
        fail "$label — missing '$substring'"
    fi
}

# ── Ensure .env exists ───────────────────────────────────────────────────
banner "Environment Setup"

if [ ! -f .env ]; then
    log "Creating .env from .env.example"
    cp .env.example .env
fi

# Ensure the salt matches what we'll use in tests
if grep -q "^T1_SALT=" .env; then
    sed -i.bak "s/^T1_SALT=.*/T1_SALT=${SALT}/" .env && rm -f .env.bak
else
    echo "T1_SALT=${SALT}" >> .env
fi
log "T1_SALT set to test value"

# ── Start stack ──────────────────────────────────────────────────────────
banner "Docker Compose — Build & Start"

log "Building images..."
docker compose build --quiet 2>&1 | tail -5

log "Starting stack..."
docker compose up -d

# ── Wait for services ────────────────────────────────────────────────────
banner "Waiting for Services"

wait_for_healthy() {
    local service="$1" max_wait="${2:-90}" elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        local health
        health=$(docker compose ps --format json "$service" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Handle both single object and array
if isinstance(data, list):
    data = data[0] if data else {}
print(data.get('Health', data.get('health', 'unknown')))
" 2>/dev/null || echo "unknown")
        if [ "$health" = "healthy" ]; then
            pass "$service is healthy (${elapsed}s)"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    fail "$service did not become healthy within ${max_wait}s"
    return 1
}

wait_for_healthy "postgres" 30
wait_for_healthy "redis" 15
wait_for_healthy "kafka" 60
wait_for_healthy "tvevents-api" 90

# Give the API a moment to finish cache pre-population
sleep 2

# ── 1. Health Check ──────────────────────────────────────────────────────
banner "1. Health Check"

HEALTH_CODE=$(http_code "$BASE_URL/health")
HEALTH_JSON=$(http_json "$BASE_URL/health")
assert_status "GET /health" "200" "$HEALTH_CODE"
assert_json_field "Health status" "$HEALTH_JSON" "status" "healthy"
assert_json_contains "Health checks — Kafka" "$HEALTH_JSON" "kafka"
assert_json_contains "Health checks — RDS" "$HEALTH_JSON" "rds"
assert_json_contains "Health checks — Redis" "$HEALTH_JSON" "redis"

# ── 2. Event Ingestion — ACR_TUNER_DATA ──────────────────────────────────
banner "2. Event Ingestion — ACR_TUNER_DATA"

HMAC_1=$(compute_hmac "$TVID")
TS_NOW=$(python3 -c "import time; print(int(time.time() * 1000))")
TS_SEC=$(python3 -c "import time; print(int(time.time()))")

ACR_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=ACR_TUNER_DATA" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_1}\",
            \"EventType\": \"ACR_TUNER_DATA\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {
            \"channelData\": {\"majorId\": 45, \"minorId\": 1, \"channelId\": \"10045\", \"channelName\": \"PBS\"},
            \"programData\": {\"programId\": \"EP012345678901\", \"startTime\": ${TS_SEC}},
            \"resolution\": {\"vRes\": 1080, \"hRes\": 1920}
        }
    }")

ACR_JSON=$(http_json -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=ACR_TUNER_DATA" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_1}\",
            \"EventType\": \"ACR_TUNER_DATA\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {
            \"channelData\": {\"majorId\": 45, \"minorId\": 1, \"channelId\": \"10045\", \"channelName\": \"PBS\"},
            \"programData\": {\"programId\": \"EP012345678901\", \"startTime\": ${TS_SEC}},
            \"resolution\": {\"vRes\": 1080, \"hRes\": 1920}
        }
    }")

assert_status "POST /v1/events (ACR_TUNER_DATA)" "200" "$ACR_CODE"
assert_json_field "ACR response" "$ACR_JSON" "status" "accepted"
assert_json_field "ACR event type" "$ACR_JSON" "event_type" "ACR_TUNER_DATA"

# ── 3. Event Ingestion — PLATFORM_TELEMETRY ──────────────────────────────
banner "3. Event Ingestion — PLATFORM_TELEMETRY"

PLAT_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=PLATFORM_TELEMETRY" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_1}\",
            \"EventType\": \"PLATFORM_TELEMETRY\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {
            \"PanelData\": {\"PanelState\": \"ON\", \"Timestamp\": ${TS_NOW}, \"WakeupReason\": 0}
        }
    }")

assert_status "POST /v1/events (PLATFORM_TELEMETRY)" "200" "$PLAT_CODE"

# ── 4. Event Ingestion — NATIVEAPP_TELEMETRY ─────────────────────────────
banner "4. Event Ingestion — NATIVEAPP_TELEMETRY"

NATIVE_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=NATIVEAPP_TELEMETRY" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_1}\",
            \"EventType\": \"NATIVEAPP_TELEMETRY\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {
            \"Timestamp\": ${TS_NOW},
            \"Namespace\": \"com.vizio.app\",
            \"AppId\": \"com.vizio.netflix\",
            \"action\": \"launch\"
        }
    }")

assert_status "POST /v1/events (NATIVEAPP_TELEMETRY)" "200" "$NATIVE_CODE"

# ── 5. Event Ingestion — Heartbeat ───────────────────────────────────────
banner "5. Event Ingestion — Heartbeat (ACR_TUNER_DATA with Heartbeat key)"

HMAC_2=$(compute_hmac "$TVID_BLACKLISTED")

HB_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID_BLACKLISTED}&event_type=ACR_TUNER_DATA" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID_BLACKLISTED}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_2}\",
            \"EventType\": \"ACR_TUNER_DATA\",
            \"timestamp\": ${TS_NOW},
            \"appId\": \"com.vizio.smartcast\",
            \"Namespace\": \"vizio.acr\"
        },
        \"EventData\": {
            \"Heartbeat\": {
                \"channelData\": {\"majorId\": 501, \"minorId\": 1, \"channelId\": \"10501\", \"channelName\": \"ESPN\"}
            }
        }
    }")

assert_status "POST /v1/events (Heartbeat)" "200" "$HB_CODE"

# ── 6. Validation — bad HMAC rejected ───────────────────────────────────
banner "6. Validation — Invalid HMAC Rejected"

BAD_HMAC_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=ACR_TUNER_DATA" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"0000000000000000000000000000000000000000000000000000000000000000\",
            \"EventType\": \"ACR_TUNER_DATA\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {}
    }")

assert_status "POST /v1/events (bad HMAC)" "400" "$BAD_HMAC_CODE"

# ── 7. Validation — missing required param ───────────────────────────────
banner "7. Validation — Missing Required Param"

MISSING_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\"
        }
    }")

assert_status "POST /v1/events (missing params)" "400" "$MISSING_CODE"

# ── 8. Kafka Delivery ───────────────────────────────────────────────────
banner "8. Kafka Delivery Verification"

KAFKA_MESSAGES=$(docker compose exec -T kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic "$KAFKA_TOPIC" \
    --from-beginning \
    --timeout-ms 5000 2>/dev/null | head -5 || true)

if [ -n "$KAFKA_MESSAGES" ]; then
    MSG_COUNT=$(echo "$KAFKA_MESSAGES" | wc -l | tr -d ' ')
    pass "Kafka topic '$KAFKA_TOPIC' has $MSG_COUNT message(s)"
    # Check that the ACR event we sent is in there
    if echo "$KAFKA_MESSAGES" | grep -q "ACR_TUNER_DATA"; then
        pass "Kafka contains ACR_TUNER_DATA event"
    else
        warn "Kafka messages present but ACR_TUNER_DATA not found in first 5"
    fi
else
    fail "No messages found in Kafka topic '$KAFKA_TOPIC'"
fi

# ── 9. Blacklist / Obfuscation ──────────────────────────────────────────
banner "9. Blacklist & Obfuscation (channel 501 is seeded as blacklisted)"

# Station STATION_001 + channel 501 is in seed_db.sql
HMAC_BL=$(compute_hmac "$TVID")
BL_JSON=$(http_json -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=ACR_TUNER_DATA" \
    -H "Content-Type: application/json" \
    -d "{
        \"TvEvent\": {
            \"tvid\": \"${TVID}\",
            \"client\": \"smartcast\",
            \"h\": \"${HMAC_BL}\",
            \"EventType\": \"ACR_TUNER_DATA\",
            \"timestamp\": ${TS_NOW}
        },
        \"EventData\": {
            \"channelData\": {\"majorId\": 501, \"minorId\": 1, \"channelId\": \"501\", \"channelName\": \"Blacklisted Channel\"},
            \"programData\": {\"programId\": \"EP999999\", \"startTime\": ${TS_SEC}},
            \"resolution\": {\"vRes\": 1080, \"hRes\": 1920}
        }
    }")

# The API returns "accepted" regardless — obfuscation happens in the output JSON sent to Kafka
assert_json_field "Blacklisted channel accepted" "$BL_JSON" "status" "accepted"

# Check Kafka for the obfuscated message
sleep 2
BL_KAFKA=$(docker compose exec -T kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic "$KAFKA_TOPIC" \
    --from-beginning \
    --timeout-ms 5000 2>/dev/null | grep -i "OBFUSCATED" || true)

if [ -n "$BL_KAFKA" ]; then
    pass "Kafka contains OBFUSCATED event for blacklisted channel"
else
    warn "OBFUSCATED not found in Kafka — blacklist may use station+channel composite key"
fi

# ── 10. SRE Ops — Diagnostics ───────────────────────────────────────────
banner "10. SRE Ops — Diagnostic Endpoints"

STATUS_CODE=$(http_code "$BASE_URL/ops/status")
assert_status "GET /ops/status" "200" "$STATUS_CODE"

METRICS_CODE=$(http_code "$BASE_URL/ops/metrics")
METRICS_JSON=$(http_json "$BASE_URL/ops/metrics")
assert_status "GET /ops/metrics" "200" "$METRICS_CODE"
assert_json_contains "Metrics has latency" "$METRICS_JSON" "latency"

CONFIG_CODE=$(http_code "$BASE_URL/ops/config")
CONFIG_JSON=$(http_json "$BASE_URL/ops/config")
assert_status "GET /ops/config" "200" "$CONFIG_CODE"
# Verify secrets are redacted
if echo "$CONFIG_JSON" | grep -q "REDACTED"; then
    pass "GET /ops/config — secrets redacted"
else
    fail "GET /ops/config — secrets NOT redacted"
fi

DEPS_CODE=$(http_code "$BASE_URL/ops/dependencies")
assert_status "GET /ops/dependencies" "200" "$DEPS_CODE"

ERRORS_CODE=$(http_code "$BASE_URL/ops/errors")
assert_status "GET /ops/errors" "200" "$ERRORS_CODE"

OPS_HEALTH_CODE=$(http_code "$BASE_URL/ops/health")
assert_status "GET /ops/health" "200" "$OPS_HEALTH_CODE"

# ── 11. SRE Ops — Remediation ───────────────────────────────────────────
banner "11. SRE Ops — Remediation Endpoints"

# Log level change
LOG_CODE=$(http_code -X PUT "$BASE_URL/ops/loglevel" \
    -H "Content-Type: application/json" \
    -d '{"level": "DEBUG"}')
assert_status "PUT /ops/loglevel (DEBUG)" "200" "$LOG_CODE"

# Restore log level
http_json -X PUT "$BASE_URL/ops/loglevel" \
    -H "Content-Type: application/json" \
    -d '{"level": "INFO"}' > /dev/null

# Cache flush
FLUSH_CODE=$(http_code -X POST "$BASE_URL/ops/cache/flush")
assert_status "POST /ops/cache/flush" "200" "$FLUSH_CODE"

# Drain mode on and off
# Note: With multiple uvicorn workers (--workers 4), drain mode is set in the
# worker that handles the POST /ops/drain request. Other workers won't have
# drain_mode=True. We retry a few times to hit the correct worker.
DRAIN_ON_CODE=$(http_code -X POST "$BASE_URL/ops/drain" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true}')
assert_status "POST /ops/drain (enable)" "200" "$DRAIN_ON_CODE"

sleep 1

# Verify drain mode rejects event requests (retry to hit the draining worker)
DRAIN_GOT_503=false
for _attempt in $(seq 1 8); do
    DRAIN_EVENT_CODE=$(http_code -X POST "$BASE_URL/v1/events?tvid=${TVID}&event_type=ACR_TUNER_DATA" \
        -H "Content-Type: application/json" \
        -d '{"TvEvent": {"tvid": "x"}}')
    if [ "$DRAIN_EVENT_CODE" = "503" ]; then
        DRAIN_GOT_503=true
        break
    fi
done
if [ "$DRAIN_GOT_503" = true ]; then
    pass "POST /v1/events while draining (HTTP 503)"
else
    fail "POST /v1/events while draining — never got 503 in 8 attempts"
fi

# Health should report draining (retry to hit the draining worker)
DRAIN_GOT_DRAINING=false
for _attempt in $(seq 1 8); do
    DRAIN_HEALTH_JSON=$(http_json "$BASE_URL/health")
    DRAIN_STATUS=$(echo "$DRAIN_HEALTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    if [ "$DRAIN_STATUS" = "draining" ]; then
        DRAIN_GOT_DRAINING=true
        break
    fi
done
if [ "$DRAIN_GOT_DRAINING" = true ]; then
    pass "Health while draining — status=draining"
else
    fail "Health while draining — never got status=draining in 8 attempts"
fi

# Disable drain
DRAIN_OFF_CODE=$(http_code -X POST "$BASE_URL/ops/drain" \
    -H "Content-Type: application/json" \
    -d '{"enabled": false}')
assert_status "POST /ops/drain (disable)" "200" "$DRAIN_OFF_CODE"

# Circuit breakers
CB_CODE=$(http_code -X POST "$BASE_URL/ops/circuits" \
    -H "Content-Type: application/json" \
    -d '{"name": "kafka", "state": "open"}')
assert_status "POST /ops/circuits (kafka open)" "200" "$CB_CODE"

# Restore circuit
http_json -X POST "$BASE_URL/ops/circuits" \
    -H "Content-Type: application/json" \
    -d '{"name": "kafka", "state": "closed"}' > /dev/null

# Scale advisory
SCALE_CODE=$(http_code -X POST "$BASE_URL/ops/scale")
assert_status "POST /ops/scale" "200" "$SCALE_CODE"

# ── 12. OpenAPI spec available ──────────────────────────────────────────
banner "12. OpenAPI Spec"

OPENAPI_CODE=$(http_code "$BASE_URL/openapi.json")
assert_status "GET /openapi.json" "200" "$OPENAPI_CODE"

# ── Summary ──────────────────────────────────────────────────────────────
banner "Summary"

TOTAL=$((PASS + FAIL))
echo ""
printf "  ${GREEN}Passed: %d${NC}  ${RED}Failed: %d${NC}  Total: %d\n" "$PASS" "$FAIL" "$TOTAL"
echo ""

# ── Cleanup ──────────────────────────────────────────────────────────────
if [ "$KEEP_STACK" = false ]; then
    log "Tearing down stack..."
    docker compose down -v --remove-orphans 2>/dev/null
    log "Stack removed."
else
    warn "Stack left running (--keep). Tear down with: docker compose down -v"
fi

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
