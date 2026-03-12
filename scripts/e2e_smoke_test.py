#!/usr/bin/env python3
"""
End-to-End Smoke Test — evergreen-tvevents
===========================================

Simulates realistic TV device payloads flowing through the entire pipeline:

  TV Device  →  POST /  →  Validation  →  Event Classification
       →  Output Generation  →  Obfuscation  →  Kafka Delivery

Exercises every component:
  1. /status endpoint (legacy backward-compat)
  2. NativeAppTelemetry event (SmartCast app usage)
  3. AcrTunerData event (content recognition — normal channel)
  4. AcrTunerData event (blacklisted channel — triggers obfuscation)
  5. AcrTunerData event (content-blocked channel — triggers obfuscation)
  6. PlatformTelemetry event (panel state change)
  7. Invalid requests (missing params, bad hash, bad JSON)
  8. /ops/* SRE endpoints (health, config, dependencies, cache, errors, drain, loglevel, metrics)

Usage:
  .venv/bin/python scripts/e2e_smoke_test.py
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import MagicMock

# ── Environment ──────────────────────────────────────────────────────────────
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["ENV"] = "dev"
os.environ["LOG_LEVEL"] = "WARNING"  # quiet app logs during test
os.environ["SERVICE_NAME"] = "evergreen-tvevents"
os.environ["T1_SALT"] = "e2e-test-salt"
os.environ["ZOO"] = "e2e-test-zoo"
os.environ["SEND_EVERGREEN"] = "true"
os.environ["SEND_LEGACY"] = "true"
os.environ["TVEVENTS_DEBUG"] = "true"
os.environ["KAFKA_TOPIC_EVERGREEN"] = "tveoe-evergreen"
os.environ["KAFKA_TOPIC_LEGACY"] = "tveoe-legacy"
os.environ["KAFKA_TOPIC_EVERGREEN_DEBUG"] = "tveoe-debug-evergreen"
os.environ["KAFKA_TOPIC_LEGACY_DEBUG"] = "tveoe-debug-legacy"
os.environ["BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH"] = "/tmp/.e2e_blacklist_cache"

# ── Mock external modules ────────────────────────────────────────────────────
# These would normally be standalone RDS/Kafka modules deployed alongside the app.
# We mock them here to run locally without infrastructure.

kafka_messages: list[dict] = []

mock_rds = MagicMock()
mock_rds.execute_query = MagicMock(
    return_value=[
        {"channel_id": "ch-blocked-999"},
        {"channel_id": "ch-adult-777"},
        {"channel_id": "ch-restricted-555"},
    ]
)
sys.modules["rds_module"] = mock_rds

mock_kafka = MagicMock()


def _capture_kafka(topic, payload_bytes, key=""):
    kafka_messages.append(
        {"topic": topic, "key": key, "payload": json.loads(payload_bytes)}
    )


mock_kafka.send_message = MagicMock(side_effect=_capture_kafka)
mock_kafka.health_check = MagicMock(return_value=True)
sys.modules["kafka_module"] = mock_kafka

mock_cnlib = MagicMock()
mock_cnlib_cnlib = MagicMock()
mock_token_hash = MagicMock()
mock_token_hash.security_hash_match = MagicMock(return_value=True)
mock_cnlib_cnlib.token_hash = mock_token_hash
mock_cnlib.cnlib = mock_cnlib_cnlib
mock_cnlib_log = MagicMock()
mock_cnlib_log.Log = MagicMock()
mock_cnlib_log.Log.return_value.LOGGER = MagicMock()
sys.modules["cnlib"] = mock_cnlib
sys.modules["cnlib.cnlib"] = mock_cnlib_cnlib
sys.modules["cnlib.cnlib.token_hash"] = mock_token_hash
sys.modules["cnlib.log"] = mock_cnlib_log


# ── Colors ───────────────────────────────────────────────────────────────────
class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def banner(text):
    w = 72
    print(f"\n{C.BOLD}{C.HEADER}{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}{C.END}")


def section(text):
    print(f"\n{C.BOLD}{C.CYAN}── {text} {'─' * (60 - len(text))}{C.END}")


def ok(msg):
    print(f"  {C.GREEN}✓{C.END} {msg}")


def fail(msg):
    print(f"  {C.RED}✗{C.END} {msg}")


def info(msg):
    print(f"  {C.DIM}│{C.END} {msg}")


def arrow(msg):
    print(f"  {C.YELLOW}→{C.END} {msg}")


def dump_json(label, obj, indent=4, max_keys=12):
    """Pretty-print a JSON object with optional truncation."""
    if isinstance(obj, dict) and len(obj) > max_keys:
        shown = dict(list(obj.items())[:max_keys])
        shown["..."] = f"({len(obj) - max_keys} more keys)"
        text = json.dumps(shown, indent=indent, default=str)
    else:
        text = json.dumps(obj, indent=indent, default=str)
    print(f"  {C.DIM}│ {label}:{C.END}")
    for line in text.split("\n"):
        print(f"  {C.DIM}│   {line}{C.END}")


# ── Payloads ─────────────────────────────────────────────────────────────────
TS = str(int(time.time() * 1000))


def make_nativeapp_payload():
    return {
        "TvEvent": {
            "tvid": "VZR2024X8K3M7N01",
            "client": "smartcast",
            "h": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            "EventType": "NATIVEAPP_TELEMETRY",
            "timestamp": TS,
        },
        "EventData": {
            "Timestamp": int(TS),
            "AppId": "com.vizio.smartcast.netflix",
            "Namespace": "smartcast_apps",
            "Data": {
                "action": "app_launch",
                "duration_ms": 3421,
                "session_id": "sess-abc-123",
            },
        },
    }


def make_acr_payload(channel_id="ch-espn-206", channel_name="ESPN", content_blocked=False):
    return {
        "TvEvent": {
            "tvid": "VZR2024Y9L4P8Q02",
            "client": "smartcast",
            "h": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
            "EventType": "ACR_TUNER_DATA",
            "timestamp": TS,
            "Namespace": "acr_content_recognition",
            "appId": "com.vizio.acr.tuner",
        },
        "EventData": {
            "channelNum": 206,
            "channelName": channel_name,
            "channelId": channel_id,
            "programId": "prog-cfb-20241114",
            "iscontentblocked": content_blocked,
            "channelData": {"majorId": 206, "minorId": 1},
            "programData": {"programdata_starttime": "1700000000"},
            "resolution": {"vRes": 1920, "hRes": 1080},
        },
    }


def make_platform_payload():
    return {
        "TvEvent": {
            "tvid": "VZR2024Z2R6S1T03",
            "client": "smartcast",
            "h": "d4c3b2a1e5f6d4c3b2a1e5f6d4c3b2a1",
            "EventType": "PLATFORM_TELEMETRY",
            "timestamp": TS,
        },
        "EventData": {
            "PanelData": {
                "PanelState": "ON",
                "WakeupReason": 1,
                "Timestamp": int(time.time()),
            },
        },
    }


def url_params_for(payload):
    tv = payload["TvEvent"]
    return {
        "tvid": tv["tvid"],
        "client": tv["client"],
        "h": tv["h"],
        "EventType": tv["EventType"],
        "event_type": tv["EventType"],
        "timestamp": tv["timestamp"],
    }


# ── Test Runner ──────────────────────────────────────────────────────────────
async def run_tests():
    from httpx import ASGITransport, AsyncClient

    from app import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    passed = 0
    failed = 0
    total_kafka = 0

    async with AsyncClient(transport=transport, base_url="http://tv-e2e") as client:

        # ──────────────────────────────────────────────────────────────────
        banner("EVERGREEN-TVEVENTS  ·  End-to-End Smoke Test")
        # ──────────────────────────────────────────────────────────────────

        # ── 1. /status ────────────────────────────────────────────────────
        section("1 · GET /status  (legacy health check)")
        r = await client.get("/status")
        if r.status_code == 200 and r.text == "OK":
            ok(f"HTTP {r.status_code}  body={r.text!r}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}  body={r.text!r}")
            failed += 1

        # ── 2. NativeAppTelemetry ─────────────────────────────────────────
        section("2 · POST /  NativeAppTelemetry  (SmartCast app → Netflix launch)")
        kafka_messages.clear()
        payload = make_nativeapp_payload()
        params = url_params_for(payload)
        dump_json("TV Device Payload", payload)
        arrow("Sending to ingestion endpoint...")

        r = await client.post("/", params=params, json=payload)
        if r.status_code == 200:
            ok(f"HTTP {r.status_code}  response={r.json()}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}  response={r.text}")
            failed += 1

        info(f"Kafka messages captured: {len(kafka_messages)}")
        for msg in kafka_messages:
            arrow(f"Topic: {msg['topic']}  Key: {msg['key']}")
            # Check NativeApp-specific fields
            p = msg["payload"]
            if "eventdata_timestamp" in p:
                ok(f"eventdata_timestamp present: {p['eventdata_timestamp']}")
            if "appid" in p:
                ok(f"appid: {p['appid']}  namespace: {p.get('namespace')}")
            dump_json("Kafka Payload", p)
        total_kafka += len(kafka_messages)

        # ── 3. AcrTunerData (normal channel) ──────────────────────────────
        section("3 · POST /  AcrTunerData  (normal channel — ESPN)")
        kafka_messages.clear()
        payload = make_acr_payload(channel_id="ch-espn-206", channel_name="ESPN")
        params = url_params_for(payload)
        dump_json("TV Device Payload", payload)
        arrow("Sending to ingestion endpoint...")

        r = await client.post("/", params=params, json=payload)
        if r.status_code == 200:
            ok(f"HTTP {r.status_code}  response={r.json()}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}  response={r.text}")
            failed += 1

        info(f"Kafka messages captured: {len(kafka_messages)}")
        for msg in kafka_messages:
            arrow(f"Topic: {msg['topic']}  Key: {msg['key']}")
            p = msg["payload"]
            # Verify NOT obfuscated
            if p.get("channelid") != "OBFUSCATED":
                ok(f"Channel NOT obfuscated: channelid={p.get('channelid')}")
            else:
                fail("Channel was obfuscated but should NOT have been")
        total_kafka += len(kafka_messages)

        # ── 4. AcrTunerData (blacklisted channel → obfuscation) ──────────
        section("4 · POST /  AcrTunerData  (BLACKLISTED channel → obfuscation)")
        kafka_messages.clear()
        payload = make_acr_payload(channel_id="ch-blocked-999", channel_name="BlockedTV")
        params = url_params_for(payload)
        info("Channel 'ch-blocked-999' is in the RDS blacklist")
        arrow("Sending to ingestion endpoint...")

        r = await client.post("/", params=params, json=payload)
        if r.status_code == 200:
            ok(f"HTTP {r.status_code}  response={r.json()}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}  response={r.text}")
            failed += 1

        info(f"Kafka messages captured: {len(kafka_messages)}")
        # With TVEVENTS_DEBUG=true and SEND_EVERGREEN+SEND_LEGACY=true:
        # debug topics get unobfuscated data, regular topics get obfuscated
        obfuscated_found = False
        unobfuscated_found = False
        for msg in kafka_messages:
            arrow(f"Topic: {msg['topic']}  Key: {msg['key']}")
            p = msg["payload"]
            if "debug" in msg["topic"]:
                if p.get("channelid") != "OBFUSCATED":
                    ok(f"Debug topic has ORIGINAL data: channelid={p.get('channelid')}")
                    unobfuscated_found = True
                dump_json("Debug Kafka Payload (pre-obfuscation)", p)
            else:
                if p.get("channelid") == "OBFUSCATED":
                    ok(f"Regular topic has OBFUSCATED data: channelid={p.get('channelid')}, programid={p.get('programid')}")
                    obfuscated_found = True
                dump_json("Kafka Payload (post-obfuscation)", p)

        if obfuscated_found:
            ok("Blacklisted channel correctly obfuscated on regular topics")
            passed += 1
        else:
            fail("Expected obfuscated data on regular topics")
            failed += 1
        if unobfuscated_found:
            ok("Debug topics received unobfuscated data before obfuscation")
            passed += 1
        else:
            fail("Expected unobfuscated data on debug topics")
            failed += 1
        total_kafka += len(kafka_messages)

        # ── 5. AcrTunerData (content-blocked → obfuscation) ──────────────
        section("5 · POST /  AcrTunerData  (iscontentblocked=true → obfuscation)")
        kafka_messages.clear()
        payload = make_acr_payload(
            channel_id="ch-normal-100", channel_name="NormalTV", content_blocked=True
        )
        params = url_params_for(payload)
        info("iscontentblocked=true triggers obfuscation regardless of blacklist")
        arrow("Sending to ingestion endpoint...")

        r = await client.post("/", params=params, json=payload)
        if r.status_code == 200:
            ok(f"HTTP {r.status_code}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}")
            failed += 1

        obfuscated_regular = any(
            m["payload"].get("channelid") == "OBFUSCATED"
            for m in kafka_messages
            if "debug" not in m["topic"]
        )
        if obfuscated_regular:
            ok("Content-blocked channel correctly obfuscated")
            passed += 1
        else:
            fail("Expected obfuscation for content-blocked channel")
            failed += 1
        total_kafka += len(kafka_messages)

        # ── 6. PlatformTelemetry ──────────────────────────────────────────
        section("6 · POST /  PlatformTelemetry  (panel state: ON)")
        kafka_messages.clear()
        payload = make_platform_payload()
        params = url_params_for(payload)
        dump_json("TV Device Payload", payload)
        arrow("Sending to ingestion endpoint...")

        r = await client.post("/", params=params, json=payload)
        if r.status_code == 200:
            ok(f"HTTP {r.status_code}  response={r.json()}")
            passed += 1
        else:
            fail(f"HTTP {r.status_code}  response={r.text}")
            failed += 1

        info(f"Kafka messages captured: {len(kafka_messages)}")
        for msg in kafka_messages:
            arrow(f"Topic: {msg['topic']}  Key: {msg['key']}")
            p = msg["payload"]
            if "paneldata_panelstate" in p:
                ok(f"PanelData flattened: paneldata_panelstate={p['paneldata_panelstate']}")
            dump_json("Kafka Payload", p)
        total_kafka += len(kafka_messages)

        # ── 7. Invalid Requests ───────────────────────────────────────────
        section("7 · Invalid Requests  (validation pipeline)")

        # 7a: Missing required params
        arrow("7a · Missing required params")
        r = await client.post(
            "/?tvid=VZR123",
            json={"TvEvent": {"tvid": "VZR123"}},
        )
        if r.status_code == 400:
            ok(f"HTTP {r.status_code}  error={r.json().get('error', '')}")
            passed += 1
        else:
            fail(f"Expected 400, got {r.status_code}")
            failed += 1

        # 7b: Invalid JSON body
        arrow("7b · Invalid JSON body")
        r = await client.post(
            "/?tvid=VZR123&client=x&h=x&EventType=X&timestamp=1",
            content=b"not-json{{{",
            headers={"content-type": "application/json"},
        )
        if r.status_code == 400:
            ok(f"HTTP {r.status_code}  error={r.json().get('error', '')}")
            passed += 1
        else:
            fail(f"Expected 400, got {r.status_code}")
            failed += 1

        # 7c: Bad security hash
        arrow("7c · Bad security hash")
        mock_token_hash.security_hash_match.return_value = False
        payload = make_nativeapp_payload()
        params = url_params_for(payload)
        r = await client.post("/", params=params, json=payload)
        if r.status_code == 400:
            ok(f"HTTP {r.status_code}  error={r.json().get('error', '')}")
            passed += 1
        else:
            fail(f"Expected 400, got {r.status_code}")
            failed += 1
        mock_token_hash.security_hash_match.return_value = True

        # ── 8. /ops/* SRE Endpoints ───────────────────────────────────────
        section("8 · /ops/* SRE Endpoints")

        ops_endpoints = [
            ("GET", "/ops/health", None, 200),
            ("GET", "/ops/config", None, 200),
            ("GET", "/ops/dependencies", None, 200),
            ("GET", "/ops/cache", None, 200),
            ("GET", "/ops/errors", None, 200),
            ("GET", "/ops/status", None, 200),
            ("GET", "/ops/metrics", None, 200),
            ("POST", "/ops/circuits", None, 200),
            ("GET", "/ops/scale", None, 200),
            ("GET", "/health", None, 200),
            ("POST", "/ops/cache/refresh", None, 200),
            ("POST", "/ops/loglevel", {"level": "INFO"}, 200),
            ("POST", "/ops/drain", {"enabled": True}, 200),
            ("POST", "/ops/drain", {"enabled": False}, 200),
        ]

        for method, path, body, expected_status in ops_endpoints:
            if method == "GET":
                r = await client.get(path)
            else:
                r = await client.post(path, json=body)

            label = f"{method:4s} {path}"
            if r.status_code == expected_status:
                try:
                    data = r.json()
                    summary = ", ".join(f"{k}={v}" for k, v in list(data.items())[:3])
                    ok(f"{label}  → {r.status_code}  [{summary}]")
                except Exception:
                    ok(f"{label}  → {r.status_code}")
                passed += 1
            else:
                fail(f"{label}  → {r.status_code} (expected {expected_status})")
                failed += 1

        # ── 9. Cache Operations ───────────────────────────────────────────
        section("9 · 3-Tier Cache Flow  (memory → file → RDS)")
        from app.blacklist import blacklist_cache

        info(f"Cache entries: {blacklist_cache.entry_count}")
        info(f"Cache age: {blacklist_cache.age_seconds:.1f}s")
        info(f"Cache file: {blacklist_cache.cache_filepath}")

        if blacklist_cache.entry_count > 0:
            ok(f"Cache populated from RDS with {blacklist_cache.entry_count} entries")
            passed += 1
        else:
            fail("Cache has no entries")
            failed += 1

        is_bl = blacklist_cache.is_blacklisted("ch-blocked-999")
        if is_bl:
            ok("is_blacklisted('ch-blocked-999') = True  ← correctly blacklisted")
            passed += 1
        else:
            fail("is_blacklisted('ch-blocked-999') should be True")
            failed += 1

        is_normal = blacklist_cache.is_blacklisted("ch-espn-206")
        if not is_normal:
            ok("is_blacklisted('ch-espn-206') = False  ← correctly not blacklisted")
            passed += 1
        else:
            fail("is_blacklisted('ch-espn-206') should be False")
            failed += 1

        # ── 10. POST /ops/cache/flush ─────────────────────────────────────
        section("10 · Cache Flush and Re-populate")
        r = await client.post("/ops/cache/flush")
        if r.status_code == 200:
            ok(f"Cache flushed: {r.json()}")
            passed += 1
        else:
            fail(f"Flush failed: {r.status_code}")
            failed += 1

        r = await client.post("/ops/cache/refresh")
        if r.status_code == 200:
            ok(f"Cache refreshed: {r.json()}")
            passed += 1
        else:
            fail(f"Refresh failed: {r.status_code}")
            failed += 1

    # ── Summary ───────────────────────────────────────────────────────────
    banner("RESULTS")
    total = passed + failed
    print(f"\n  {C.GREEN}{passed}{C.END} passed  ·  {C.RED}{failed}{C.END} failed  ·  {total} total checks")
    print(f"  {C.BLUE}{total_kafka}{C.END} Kafka messages captured across all event types")
    print(f"  {C.BLUE}{mock_kafka.send_message.call_count}{C.END} total kafka_module.send_message() calls")
    print(f"  {C.BLUE}{mock_rds.execute_query.call_count}{C.END} total rds_module.execute_query() calls")
    print()

    # ── Data Flow Diagram ─────────────────────────────────────────────────
    banner("DATA FLOW — What This Test Exercised")
    print(f"""
  {C.BOLD}TV Device{C.END}
      │
      │  POST /?tvid=VZR...&EventType=...&h=...&timestamp=...
      │  Body: {{"TvEvent": {{...}}, "EventData": {{...}}}}
      ▼
  {C.BOLD}FastAPI Ingestion (/){C.END}
      │
      ├─ {C.CYAN}Validation{C.END}
      │   ├─ verify_required_params()       — all TvEvent keys present
      │   ├─ params_match_check()           — URL params match body
      │   ├─ timestamp_check()              — parseable ms timestamp
      │   ├─ validate_security_hash()       — T1_SALT via cnlib
      │   └─ validate_event_type_payload()  — EventData schema check
      │
      ├─ {C.CYAN}Event Classification{C.END}
      │   ├─ NativeAppTelemetryEventType    — SmartCast app telemetry
      │   ├─ AcrTunerDataEventType          — ACR content recognition
      │   └─ PlatformTelemetryEventType     — panel state changes
      │
      ├─ {C.CYAN}Output Generation{C.END}
      │   ├─ flatten_request_json()         — nested → flat keys
      │   ├─ generate_output_json()         — merge TvEvent + EventData
      │   └─ eventdata_timestamp / appid / namespace injected
      │
      ├─ {C.CYAN}Obfuscation (conditional){C.END}
      │   ├─ blacklist_cache.is_blacklisted()  — 3-tier: memory→file→RDS
      │   ├─ iscontentblocked check
      │   └─ channelid/programid/channelname → "OBFUSCATED"
      │
      └─ {C.CYAN}Kafka Delivery{C.END}
          ├─ Debug topics  (unobfuscated, if TVEVENTS_DEBUG=true)
          ├─ tveoe-evergreen        (if SEND_EVERGREEN=true)
          └─ tveoe-legacy           (if SEND_LEGACY=true)

  {C.BOLD}/ops/* SRE Endpoints{C.END}
      ├─ /ops/health       — deep health (RDS + Kafka + cache)
      ├─ /ops/config       — runtime configuration
      ├─ /ops/dependencies — external dependency status
      ├─ /ops/cache        — cache statistics
      ├─ /ops/errors       — error summary
      ├─ /ops/status       — overall service verdict
      ├─ /ops/metrics      — golden signal metrics
      ├─ /ops/circuits     — circuit breaker state
      ├─ /ops/scale        — scaling info
      ├─ /ops/loglevel     — runtime log level change
      ├─ /ops/drain        — drain mode toggle
      └─ /ops/cache/flush  — cache flush + refresh
""")

    if failed > 0:
        print(f"  {C.RED}{C.BOLD}⚠  {failed} check(s) failed — review output above{C.END}\n")
        return 1
    else:
        print(f"  {C.GREEN}{C.BOLD}✓  All checks passed — pipeline fully functional{C.END}\n")
        return 0


# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
