#!/usr/bin/env bash
set -euo pipefail

# Full end-to-end test for tvevents-k8s
#
# Tests the complete ingestion path: HTTP → validate → transform → obfuscate → Kafka
#
# Prerequisites:
#   docker compose up -d postgres kafka
#   Kafka topics created: test-evergreen, test-legacy
#   App running with SEND_EVERGREEN=true SEND_LEGACY=true
#
# Usage: ./scripts/e2e-full.sh [BASE_URL] [SALT]

BASE_URL="${1:-http://localhost:8000}"
SALT="${2:-test-salt}"
PASS=0
FAIL=0

green() { printf '\033[0;32m  PASS: %s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m  FAIL: %s\033[0m\n' "$1"; }

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        green "$name"
        PASS=$((PASS + 1))
    else
        red "$name (expected='$expected', got='$actual')"
        FAIL=$((FAIL + 1))
    fi
}

check_contains() {
    local name="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -q "$needle"; then
        green "$name"
        PASS=$((PASS + 1))
    else
        red "$name (expected to contain '$needle')"
        FAIL=$((FAIL + 1))
    fi
}

md5hash() {
    python3 -c "import hashlib; print(hashlib.md5('${1}${SALT}'.encode()).hexdigest())"
}

echo "============================================"
echo "  tvevents-k8s Full E2E Test"
echo "============================================"
echo "Target: $BASE_URL"
echo ""

# -----------------------------------------------
# Phase 1: Health & Ops Endpoints
# -----------------------------------------------
echo "--- Phase 1: Health & Ops ---"

echo "1. GET /status"
check "HTTP 200" "200" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/status")"

echo "2. GET /health"
check "HTTP 200" "200" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/health")"

echo "3. GET /ops/status"
OPS_STATUS=$(curl -s "$BASE_URL/ops/status")
check "service=tvevents-k8s" "tvevents-k8s" "$(echo "$OPS_STATUS" | jq -r '.service')"

echo "4. GET /ops/health"
OPS_HEALTH=$(curl -s "$BASE_URL/ops/health")
RDS_HEALTHY=$(echo "$OPS_HEALTH" | jq -r '.dependencies[] | select(.name=="rds") | .healthy')
KAFKA_HEALTHY=$(echo "$OPS_HEALTH" | jq -r '.dependencies[] | select(.name=="kafka") | .healthy')
check "RDS healthy" "true" "$RDS_HEALTHY"
check "Kafka healthy" "true" "$KAFKA_HEALTHY"

echo "5. GET /ops/config"
OPS_CONFIG=$(curl -s "$BASE_URL/ops/config")
check "service_name" "tvevents-k8s" "$(echo "$OPS_CONFIG" | jq -r '.service_name')"
check "no secrets leaked" "false" "$(echo "$OPS_CONFIG" | jq 'has("t1_salt")')"

echo "6. GET /ops/metrics"
check "HTTP 200" "200" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/ops/metrics")"

echo "7. GET /ops/circuits"
check "rds circuit closed" "closed" "$(curl -s "$BASE_URL/ops/circuits" | jq -r '.circuits.rds')"

echo "8. POST /ops/loglevel"
check "loglevel changed" "DEBUG" "$(curl -s -X POST -H 'Content-Type: application/json' -d '{"level":"DEBUG"}' "$BASE_URL/ops/loglevel" | jq -r '.current')"
curl -s -X POST -H 'Content-Type: application/json' -d '{"level":"INFO"}' "$BASE_URL/ops/loglevel" > /dev/null

echo "9. POST /ops/drain (toggle on/off)"
check "drain on" "true" "$(curl -s -X POST "$BASE_URL/ops/drain" | jq -r '.draining')"
check "drain off" "false" "$(curl -s -X POST "$BASE_URL/ops/drain" | jq -r '.draining')"

echo "10. GET /openapi.json"
check "HTTP 200" "200" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/openapi.json")"

echo ""

# -----------------------------------------------
# Phase 2: Validation
# -----------------------------------------------
echo "--- Phase 2: Validation ---"

echo "11. POST / with empty body"
check "400 on empty body" "400" "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' "$BASE_URL/?tvid=x&event_type=ACR_TUNER_DATA")"

echo "12. POST / with bad hash"
BODY=$(curl -s -X POST -H 'Content-Type: application/json' \
  "http://localhost:8000/?tvid=badhash&event_type=ACR_TUNER_DATA" \
  -d '{"TvEvent":{"tvid":"badhash","client":"e2e","h":"0000000000000000","EventType":"ACR_TUNER_DATA","timestamp":1700000000000},"EventData":{"channelData":{"channelid":"1","channelname":"x","majorId":1,"minorId":0},"programData":{"programid":"P1","starttime":1700000000}}}')
check "security error on bad hash" "TvEventsSecurityValidationError" "$(echo "$BODY" | jq -r '.error')"

echo ""

# -----------------------------------------------
# Phase 3: Full Ingestion — Normal Channel
# -----------------------------------------------
echo "--- Phase 3: Ingestion (normal channel) ---"

TVID_NORMAL="e2e-normal-$(date +%s)"
HASH_NORMAL=$(md5hash "$TVID_NORMAL")

echo "13. POST / with valid payload (channel=99999)"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  "$BASE_URL/?tvid=${TVID_NORMAL}&event_type=ACR_TUNER_DATA" \
  -d "{\"TvEvent\":{\"tvid\":\"$TVID_NORMAL\",\"client\":\"e2e-test\",\"h\":\"$HASH_NORMAL\",\"EventType\":\"ACR_TUNER_DATA\",\"timestamp\":1700000000000},\"EventData\":{\"channelData\":{\"channelid\":\"99999\",\"channelname\":\"SafeChannel\",\"majorId\":1,\"minorId\":0},\"programData\":{\"programid\":\"PROG001\",\"starttime\":1700000000}}}")
check "HTTP 200 on valid payload" "200" "$HTTP"

# Give Kafka a moment to flush
sleep 1

echo "14. Verify message in Kafka (test-evergreen)"
KAFKA_MSG=$(docker compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-evergreen --from-beginning --timeout-ms 5000 2>/dev/null | grep "$TVID_NORMAL" || true)
check_contains "message in evergreen topic" "$TVID_NORMAL" "$KAFKA_MSG"
check_contains "channelid=99999 (not obfuscated)" "99999" "$KAFKA_MSG"

echo "15. Verify message in Kafka (test-legacy)"
KAFKA_MSG_LEGACY=$(docker compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-legacy --from-beginning --timeout-ms 5000 2>/dev/null | grep "$TVID_NORMAL" || true)
check_contains "message in legacy topic" "$TVID_NORMAL" "$KAFKA_MSG_LEGACY"

echo ""

# -----------------------------------------------
# Phase 4: Full Ingestion — Blacklisted Channel
# -----------------------------------------------
echo "--- Phase 4: Ingestion (blacklisted channel) ---"

TVID_BLACK="e2e-blacklist-$(date +%s)"
HASH_BLACK=$(md5hash "$TVID_BLACK")

echo "16. POST / with blacklisted channel (channel=12345)"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  "$BASE_URL/?tvid=${TVID_BLACK}&event_type=ACR_TUNER_DATA" \
  -d "{\"TvEvent\":{\"tvid\":\"$TVID_BLACK\",\"client\":\"e2e-test\",\"h\":\"$HASH_BLACK\",\"EventType\":\"ACR_TUNER_DATA\",\"timestamp\":1700000000000},\"EventData\":{\"channelData\":{\"channelid\":\"12345\",\"channelname\":\"BlacklistedChan\",\"majorId\":5,\"minorId\":0},\"programData\":{\"programid\":\"PROG999\",\"starttime\":1700000000}}}")
check "HTTP 200 on blacklisted payload" "200" "$HTTP"

sleep 1

echo "17. Verify obfuscation in Kafka (test-evergreen)"
KAFKA_BL=$(docker compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-evergreen --from-beginning --timeout-ms 5000 2>/dev/null | grep "$TVID_BLACK" || true)
check_contains "message in evergreen topic" "$TVID_BLACK" "$KAFKA_BL"
check_contains "channelid OBFUSCATED" "OBFUSCATED" "$KAFKA_BL"

echo "18. Verify obfuscation in Kafka (test-legacy)"
KAFKA_BL_L=$(docker compose exec -T kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-legacy --from-beginning --timeout-ms 5000 2>/dev/null | grep "$TVID_BLACK" || true)
check_contains "legacy topic obfuscated" "OBFUSCATED" "$KAFKA_BL_L"

echo ""

# -----------------------------------------------
# Phase 5: Verify Transform Output Structure
# -----------------------------------------------
echo "--- Phase 5: Output structure ---"

echo "19. Verify flattened keys"
check_contains "has tvid" "\"tvid\"" "$KAFKA_MSG"
check_contains "has tvevent_timestamp" "tvevent_timestamp" "$KAFKA_MSG"
check_contains "has tvevent_eventtype" "tvevent_eventtype" "$KAFKA_MSG"
check_contains "has channeldata_channelid" "channeldata_channelid" "$KAFKA_MSG"
check_contains "has programdata_programid" "programdata_programid" "$KAFKA_MSG"
check_contains "has programdata_starttime" "programdata_starttime" "$KAFKA_MSG"
check_contains "has zoo" "\"zoo\"" "$KAFKA_MSG"

echo ""

# -----------------------------------------------
# Summary
# -----------------------------------------------
TOTAL=$((PASS + FAIL))
echo "============================================"
echo "  Results: $PASS/$TOTAL passed, $FAIL failed"
echo "============================================"
if [ "$FAIL" -gt 0 ]; then
    red "E2E TEST FAILED"
    exit 1
else
    green "E2E TEST PASSED"
    exit 0
fi
