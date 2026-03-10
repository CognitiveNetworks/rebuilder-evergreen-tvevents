# Data Migration Mapping

> Schema mapping between the legacy tvevents-k8s application and the target system.

## Overview

**No data migration is required.** The tvevents-k8s service is stateless — it reads from a shared RDS PostgreSQL table (read-only) and writes to delivery streams (Firehose → Kafka). The service does not own any database schema. The file-based cache is ephemeral and regenerated at every pod startup.

## Source: AWS RDS PostgreSQL

The service accesses a single table via a single read-only query:

| Legacy Table | Legacy Column | Type | Target Table | Target Column | Type | Transformation |
|---|---|---|---|---|---|---|
| `public.tvevents_blacklisted_station_channel_map` | `channel_id` | `varchar` | `public.tvevents_blacklisted_station_channel_map` | `channel_id` | `varchar` | Direct copy — same table, same instance |

**Query (unchanged):**
```sql
SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map
```

## File Cache Schema

| Item | Legacy | Target | Transformation |
|---|---|---|---|
| File path | `/tmp/.blacklisted_channel_ids_cache` | `/tmp/.blacklisted_channel_ids_cache` | Direct copy — same path |
| Format | JSON array of channel ID strings | JSON array of channel ID strings | Direct copy — same format |
| Population | RDS query at startup (entrypoint.sh) + cache-miss fallback | RDS query at startup (entrypoint.sh) + cache-miss fallback | Same logic |

## Event Payload Schema (Input)

The TV event payload structure is preserved exactly. No transformation of the input format.

| Field Path | Type | Required | Notes |
|---|---|---|---|
| `TvEvent.tvid` | string | Yes | TV device identifier (hashed MAC) |
| `TvEvent.client` | string | Yes | Client identifier |
| `TvEvent.h` | string | Yes | HMAC security hash |
| `TvEvent.EventType` | string | Yes | ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, or PLATFORM_TELEMETRY |
| `TvEvent.timestamp` | string | Yes | Unix timestamp in milliseconds |
| `EventData.*` | object | Yes | Event-type-specific fields (varies by EventType) |

## Event Payload Schema (Output)

The flattened output JSON structure is preserved exactly. The only change is the delivery mechanism (Kafka instead of Firehose).

| Output Field | Source | Transformation |
|---|---|---|
| `tvid` | `TvEvent.tvid` | Direct copy (lowercased key) |
| `client` | `TvEvent.client` | Direct copy |
| `h` | `TvEvent.h` | Direct copy |
| `zoo` | `FLASK_ENV` env var | Renamed to app config; same value |
| `tvevent_timestamp` | `TvEvent.timestamp` | Direct copy |
| `tvevent_eventtype` | `TvEvent.EventType` | Direct copy |
| `namespace` | `EventData.Namespace` | Extracted for NATIVEAPP_TELEMETRY |
| `appid` | `EventData.AppId` | Extracted for NATIVEAPP_TELEMETRY |
| `channelid` | `EventData.channelData.channelid` | Obfuscated if blacklisted |
| `programid` | `EventData.programData.programid` | Obfuscated if blacklisted |
| `channelname` | `EventData.channelData.channelname` | Obfuscated if blacklisted |
| `programdata_starttime` | `EventData.programData.programdata_starttime` | Converted from seconds to milliseconds (ACR_TUNER_DATA) |
| *(remaining EventData fields)* | `EventData.*` | Flattened and lowercased |

## Delivery Stream → Kafka Topic Mapping

| Legacy Firehose Stream | Environment Variable | Target Kafka Topic | Notes |
|---|---|---|---|
| `tveoe-evergreen` | `EVERGREEN_FIREHOSE_NAME` → `KAFKA_TOPIC_EVERGREEN` | `[TODO: topic name]` | Primary analytics pipeline |
| `tveoe-legacy` | `LEGACY_FIREHOSE_NAME` → `KAFKA_TOPIC_LEGACY` | `[TODO: topic name]` | Backward-compatible pipeline |
| `tveoe-debug-evergreen` | `DEBUG_EVERGREEN_FIREHOSE_NAME` → `KAFKA_TOPIC_DEBUG_EVERGREEN` | `[TODO: topic name]` | Debug (pre-obfuscation) |
| `tveoe-debug-legacy` | `DEBUG_LEGACY_FIREHOSE_NAME` → `KAFKA_TOPIC_DEBUG_LEGACY` | `[TODO: topic name]` | Debug (pre-obfuscation) |

## Mapping Notes

- **No schema changes.** The service does not own any database schema. The RDS table is shared and read-only from this service's perspective.
- **No columns dropped.** The single `channel_id` column query is unchanged.
- **No new columns.** No target schema changes in the database.
- **Output format unchanged.** The flattened JSON output structure is identical — only the delivery mechanism changes (Kafka for Firehose).
- **Environment variable rename.** Firehose stream name env vars are renamed to Kafka topic name env vars. Values change (stream names → topic names).

## Edge Cases

- **Null handling:** `channel_id` nulls in RDS are filtered by `DISTINCT`. No null channel IDs in the cache.
- **Encoding:** All strings are UTF-8. No character set conversions needed.
- **Timestamp format:** Input timestamps are Unix milliseconds (string). `programdata_starttime` is converted from seconds to milliseconds for ACR_TUNER_DATA events. This logic is preserved exactly.

## Reconciliation Queries

| Check | Legacy Query | Target Query | Expected |
|---|---|---|---|
| Blacklist channel count | `SELECT COUNT(DISTINCT channel_id) FROM public.tvevents_blacklisted_station_channel_map` | `SELECT COUNT(DISTINCT channel_id) FROM public.tvevents_blacklisted_station_channel_map` | Match — same table, same instance |
| Cache file content | `python -c "import json; print(len(json.load(open('/tmp/.blacklisted_channel_ids_cache'))))"` | `python -c "import json; print(len(json.load(open('/tmp/.blacklisted_channel_ids_cache'))))"` | Match — same format, same content |
