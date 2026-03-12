# Data Migration Mapping

> Schema mapping between the legacy application and the target system.
> This is a simple migration: the application is read-only against the database, the schema is unchanged, and the cache format is preserved.

## Overview

This service performs **no schema changes** to the database. The `public.tvevents_blacklisted_station_channel_map` table is read-only from this application's perspective and is shared with other consumers. The rebuild connects to the same RDS instance, same table, using the same query — routed through a standalone RDS module instead of inline psycopg2.

The primary "migration" is configuration: replacing AWS Kinesis Firehose stream names with Apache Kafka topic names, and updating environment variables accordingly.

## Source: PostgreSQL RDS — tvevents database

### Schema Mapping

| Legacy Table | Legacy Column | Type | Target Table | Target Column | Type | Transformation |
|---|---|---|---|---|---|---|
| public.tvevents_blacklisted_station_channel_map | channel_id | (inferred from SELECT DISTINCT usage) | public.tvevents_blacklisted_station_channel_map | channel_id | (unchanged) | Direct — no transformation. Same table, same column, same RDS instance. |

> **Note:** This service only reads `channel_id` via `SELECT DISTINCT channel_id`. Additional columns may exist in the table but are not consumed by this application and are therefore not mapped.

### Application Query

| Query | Legacy Implementation | Target Implementation | Change |
|---|---|---|---|
| Blacklist lookup | `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map` via inline psycopg2 in `dbhelper.py` | Same query via standalone RDS module with connection pooling | Transport only — query unchanged, results identical |

## Cache File Mapping

| Aspect | Legacy | Target | Change |
|---|---|---|---|
| Format | JSON array of channel IDs (`json.dump` / `json.load`) | JSON array of channel IDs (`json.dump` / `json.load`) | None |
| Location | `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` env var (default `/tmp/.blacklisted_channel_ids_cache`) | `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` env var (same default) | None |
| Refresh trigger | Container startup + periodic refresh | Container startup + periodic refresh | None |
| Tier fallback | Memory → File → RDS | Memory → File → RDS (via standalone module) | Transport to RDS changes, fallback logic unchanged |

## Delivery Stream → Kafka Topic Mapping

| Legacy Firehose Stream (env var) | Kafka Topic (env var) | Proposed Topic Name | Routing Condition | Payload Change |
|---|---|---|---|---|
| EVERGREEN_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN | evergreen-tvevents | SEND_EVERGREEN=True | None — JSON byte-for-byte identical |
| EVERGREEN_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN_DEBUG | evergreen-tvevents-debug | SEND_EVERGREEN=True | None |
| LEGACY_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY | legacy-tvevents | SEND_LEGACY=True | None |
| LEGACY_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY_DEBUG | legacy-tvevents-debug | SEND_LEGACY=True | None |
| (ACR variant) | KAFKA_TOPIC_ACR | acr-tvevents | EventType=AcrTunerData | None |
| (ACR debug variant) | KAFKA_TOPIC_ACR_DEBUG | acr-tvevents-debug | EventType=AcrTunerData | None |
| (Platform variant) | KAFKA_TOPIC_PLATFORM | platform-tvevents | EventType=PlatformTelemetry | None |
| (Platform debug variant) | KAFKA_TOPIC_PLATFORM_DEBUG | platform-tvevents-debug | EventType=PlatformTelemetry | None |

> **Critical:** JSON payloads delivered to Kafka topics must be byte-for-byte identical to what was delivered to Firehose streams. Downstream analytics consumers expect the same format. Parity tests with captured Firehose output fixtures are required.

## Environment Variable Migration

| Legacy Variable | Target Variable | Action | Notes |
|---|---|---|---|
| EVERGREEN_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN | Rename | Value changes from Firehose stream name to Kafka topic name |
| EVERGREEN_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN_DEBUG | Rename | Same |
| LEGACY_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY | Rename | Same |
| LEGACY_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY_DEBUG | Rename | Same |
| SEND_EVERGREEN | SEND_EVERGREEN | Keep | Boolean flag, unchanged |
| SEND_LEGACY | SEND_LEGACY | Keep | Boolean flag, unchanged |
| T1_SALT | T1_SALT | Keep | Security hash salt, unchanged |
| BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH | BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH | Keep | Cache file path, unchanged |
| DB_HOST | DB_HOST | Keep | RDS endpoint (via standalone module) |
| DB_PORT | DB_PORT | Keep | RDS port |
| DB_NAME | DB_NAME | Keep | Database name |
| DB_USER | DB_USER | Keep | Database user |
| DB_PASSWORD | DB_PASSWORD | Keep | Database password (from Kubernetes Secret) |
| FLASK_ENV | (dropped) | Drop | Not needed with FastAPI/uvicorn |
| FLASK_APP | (dropped) | Drop | Not needed with FastAPI/uvicorn |
| — | KAFKA_BROKERS | Add | New: comma-separated Kafka broker addresses |
| — | KAFKA_SECURITY_PROTOCOL | Add | New: SASL_SSL or PLAINTEXT |
| — | KAFKA_SASL_MECHANISM | Add | New: e.g., SCRAM-SHA-512 |
| — | KAFKA_USERNAME | Add | New: SASL username (from Kubernetes Secret) |
| — | KAFKA_PASSWORD | Add | New: SASL password (from Kubernetes Secret) |
| — | OTEL_EXPORTER_OTLP_ENDPOINT | Add/Keep | OTLP collector endpoint (may already exist) |
| — | OTEL_SERVICE_NAME | Add/Keep | Service name for telemetry |

## Mapping Notes

- **No DDL required.** The target database schema is identical to the source. This service does not own the table and performs no writes.
- **No data migration script needed.** The same RDS instance serves both legacy and rebuilt services.
- **Cache file format is frozen.** The JSON array format (`[channel_id_1, channel_id_2, ...]`) must not change. The rebuilt service reads cache files written by the legacy service during canary/cutover phases.
- **Firehose → Kafka is a configuration migration, not a data migration.** The JSON payload format is preserved; only the transport changes.
- **FLASK_ENV and FLASK_APP are dropped** because FastAPI/uvicorn does not use them. No replacement needed.
- **New Kafka variables are required** for broker authentication. These must be provisioned as Kubernetes Secrets before deployment.
- **DB connection variables are unchanged** but are now consumed by the standalone RDS module instead of inline psycopg2 in dbhelper.py.

## Edge Cases

- **Null channel_ids:** The SELECT DISTINCT query may return null channel_ids if the table contains NULL values. Both legacy and target handle this identically — NULLs are included in the in-memory set. No special handling needed.
- **Empty blacklist table:** If the table contains zero rows, the cache is an empty list. The legacy behavior (no obfuscation for anyone) is preserved.
- **Cache file missing on startup:** If BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH does not exist, the service falls back to RDS query. If RDS is also unreachable, the service starts with an empty cache and logs a warning. Same behavior in legacy and target.
- **Cache file written by legacy service:** During canary/cutover, the legacy service may write the cache file. The rebuilt service reads it. Format compatibility is guaranteed (same JSON structure).
- **Encoding:** Channel IDs are numeric or simple ASCII strings. No character encoding issues.
- **Timezone:** Not applicable — no timestamp columns consumed by this service from the blacklist table.

## Reconciliation Queries

> Queries to validate data integrity during parallel-run and after cutover.

| Check | Query | Expected Result |
|---|---|---|
| Row count matches | `SELECT COUNT(DISTINCT channel_id) FROM public.tvevents_blacklisted_station_channel_map` | Same result from both legacy and rebuilt service connections (same RDS instance) |
| Cache file entry count | Compare `len(json.load(cache_file))` on legacy pod vs rebuilt pod | Identical counts (same source data) |
| Memory cache entry count | `GET /ops/cache` on rebuilt service → `entries` field | Matches row count from RDS query |
| Kafka payload parity | Capture Firehose output JSON, compare against Kafka message JSON for same input event | Byte-for-byte identical |
| Delivery success rate | `GET /ops/health` on rebuilt service → Kafka status | `status: ok` with latency < 50ms |
| Cache freshness | `GET /ops/cache` on rebuilt service → `age_seconds` field | Within expected refresh interval |
