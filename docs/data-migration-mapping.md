# Data Migration Mapping

> Schema and data-flow mapping between the legacy **evergreen-tvevents** application
> and the rebuilt **rebuilder-evergreen-tvevents** service.
>
> **Special case:** There is **no database migration.** The legacy application is
> read-only against PostgreSQL (AWS RDS) — it never writes to the
> `tvevents_blacklisted_station_channel_map` table. The rebuild connects to the
> same RDS instance and queries the same table with the same SQL. No schema
> changes occur.
>
> The two data-related changes are:
> 1. **Cache layer:** File-based cache (`/tmp/.blacklisted_channel_ids_cache`) →
>    Redis SET (`tvevents:blacklisted_channels`) via `rebuilder-redis-module`.
> 2. **Event delivery:** AWS Kinesis Data Firehose → Apache Kafka. The flattened
>    JSON output format is preserved exactly; only the transport changes.
>
> This document catalogs every data store, key pattern, field mapping, and
> transformation for completeness and as a developer reference.

## Migration Strategy

No data migration. The strategy is:

1. **Phase 1 (Build):** The new service is built to query the same RDS table,
   produce the same flattened JSON output schema, and cache blacklisted channel
   IDs in Redis instead of a local file.
2. **Phase 2 (Parallel Run):** Both legacy and new services run simultaneously.
   Traffic is split via Kong/load balancer configuration. Both services read
   from the same RDS table (read-only, no write conflicts). Legacy writes to
   Firehose; rebuild writes to Kafka. Downstream consumers are configured to
   read from both sinks during the transition.
3. **Phase 3 (Cutover):** Legacy service is decommissioned. All traffic routes
   to the rebuild. Firehose streams are decommissioned after downstream
   consumers fully migrate to Kafka topics.

**Risk:** During Phase 2, both systems read from the same RDS table — this is
safe because the application is read-only. The cache layers are independent
(file vs. Redis) so there is no cache contention. Event output goes to
different sinks (Firehose vs. Kafka) so there is no write conflict.

## Data Store Inventory

| # | Store | Type | Legacy Location | Target Location | Migration Phase |
|---|---|---|---|---|---|
| 1 | RDS PostgreSQL (`tvevents_blacklisted_station_channel_map`) | Amazon RDS | psycopg2 direct connection | asyncpg async pool (read-only) | No migration — shared |
| 2 | Blacklist cache (file) | Local filesystem | `/tmp/.blacklisted_channel_ids_cache` | N/A — replaced by Redis | Replaced at cutover |
| 3 | Blacklist cache (Redis) | ElastiCache Redis | N/A — does not exist in legacy | `tvevents:blacklisted_channels` SET via `rebuilder-redis-module` | New in rebuild |
| 4 | AWS Kinesis Data Firehose | Streaming | boto3 via cnlib `firehose.Firehose` | N/A — replaced by Kafka | Decommissioned at cutover |
| 5 | Apache Kafka | Streaming | N/A — does not exist in legacy | confluent-kafka producer | New in rebuild |

## Relational Databases

### Source: RDS PostgreSQL — `tvevents_blacklisted_station_channel_map`

**Consuming service (legacy):** evergreen-tvevents (`app/dbhelper.py` via psycopg2)
**Consuming service (target):** rebuilder-evergreen-tvevents (asyncpg, read-only async pool)
**Migration:** None — target connects to the same RDS instance and table.

| Legacy Table | Legacy Column | Type | Target Table | Target Column | Type | Transformation |
|---|---|---|---|---|---|---|
| `public.tvevents_blacklisted_station_channel_map` | `channel_id` | varchar | `public.tvevents_blacklisted_station_channel_map` | `channel_id` | varchar | Direct — same table, same column |

**Query — Legacy:**
```sql
SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map;
```

**Query — Target:**
```sql
SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map;
```

Identical query. The result set is loaded into the blacklist cache (file in
legacy, Redis SET in rebuild).

#### Mapping Notes

- No schema changes. The table is not modified by the rebuild.
- The application is **read-only** against this table. It never writes, updates,
  or deletes rows. Schema management is external (unknown admin tools or batch
  processes write to this table).
- The legacy service opens a new psycopg2 connection per query (no connection
  pooling). The target service uses an asyncpg connection pool for efficiency.
- No columns are dropped, added, or transformed.

## Key-Value / Cache Stores

### Cache Migration — Blacklisted Channel IDs (File → Redis)

This is the primary data-related change in the rebuild. The legacy three-tier
cache (in-memory → file → RDS) is replaced with a two-tier cache
(Redis SET → RDS).

#### Legacy Cache Architecture

```
┌──────────────────────────────┐
│  In-memory Python set        │  ← First check (per-process)
│  (populated on startup or    │
│   from file cache)           │
└──────────────┬───────────────┘
               │ miss
               ▼
┌──────────────────────────────┐
│  File cache                  │  ← Second check
│  /tmp/.blacklisted_channel_  │     Shared within pod filesystem
│  ids_cache                   │     Lost on pod restart
└──────────────┬───────────────┘
               │ miss
               ▼
┌──────────────────────────────┐
│  PostgreSQL RDS              │  ← Source of truth
│  SELECT DISTINCT channel_id  │     New connection per query
│  FROM public.tvevents_       │     Result written to file cache
│  blacklisted_station_        │     + in-memory set
│  channel_map                 │
└──────────────────────────────┘
```

**Problems:**
- File cache is not shared across pods (300–500 production pods each maintain
  their own copy).
- File cache is lost on pod restart, causing a thundering-herd RDS query storm.
- No connection pooling — every cache miss opens a new psycopg2 connection.
- In-memory set is per-Gunicorn-worker — gevent workers within a process share,
  but separate Gunicorn workers do not.

#### Target Cache Architecture

```
┌──────────────────────────────┐
│  Redis SET                   │  ← First check (shared across all pods)
│  tvevents:blacklisted_       │     TTL: 300s (5 min)
│  channels                    │     Via rebuilder-redis-module
└──────────────┬───────────────┘
               │ miss / expired
               ▼
┌──────────────────────────────┐
│  PostgreSQL RDS              │  ← Source of truth
│  SELECT DISTINCT channel_id  │     asyncpg connection pool
│  FROM public.tvevents_       │     Result written to Redis SET
│  blacklisted_station_        │     with 300s TTL
│  channel_map                 │
└──────────────────────────────┘
```

**Improvements:**
- Redis SET is shared across all pods — a single cache for the entire fleet.
- 300s TTL ensures automatic refresh without thundering-herd on restart.
- asyncpg connection pool eliminates per-query connection overhead.
- No local filesystem dependency.

#### Redis Key Pattern

| # | Key Pattern | Example | Data Type | TTL | Source | Migration Approach |
|---|---|---|---|---|---|---|
| 1 | `tvevents:blacklisted_channels` | `tvevents:blacklisted_channels` | SET of strings | 300s (5 min) | RDS query result | New — no legacy equivalent |

**Redis operations used:**

| Operation | Command | Purpose |
|---|---|---|
| Check if populated | `EXISTS tvevents:blacklisted_channels` | Determine if cache is warm |
| Check membership | `SISMEMBER tvevents:blacklisted_channels {channel_id}` | Check if a channel is blacklisted |
| Populate cache | `SADD tvevents:blacklisted_channels {id1} {id2} ...` | Bulk-add all blacklisted IDs from RDS |
| Set expiry | `EXPIRE tvevents:blacklisted_channels 300` | 5-minute TTL auto-refresh |
| Full read (debug) | `SMEMBERS tvevents:blacklisted_channels` | Retrieve all members (diagnostic use only) |
| Count (diagnostic) | `SCARD tvevents:blacklisted_channels` | Count of cached blacklisted channels |

**Cache refresh logic (target):**
```python
# Pseudocode — rebuilder-evergreen-tvevents cache refresh
async def get_blacklisted_channels(redis_client, rds_pool) -> set[str]:
    if await redis_client.exists("tvevents:blacklisted_channels"):
        return await redis_client.smembers("tvevents:blacklisted_channels")

    # Cache miss — query RDS
    async with rds_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT channel_id "
            "FROM public.tvevents_blacklisted_station_channel_map"
        )
    channel_ids = {row["channel_id"] for row in rows}

    if channel_ids:
        await redis_client.sadd("tvevents:blacklisted_channels", *channel_ids)
        await redis_client.expire("tvevents:blacklisted_channels", 300)

    return channel_ids
```

**Fallback:** If Redis is unreachable, the service falls back to an in-memory
cache populated directly from RDS (per the dependency contract in
`scope.md`). This mirrors the legacy behavior of falling back to RDS when the
file cache is unavailable.

## Event Delivery — Firehose → Kafka

### Transport Migration

The flattened JSON event output is delivered to Kafka topics instead of Kinesis
Data Firehose streams. The **JSON schema is preserved exactly** — downstream
consumers receive byte-compatible records.

| Legacy Mechanism | Target Mechanism | Transformation |
|---|---|---|
| AWS Kinesis Data Firehose (via cnlib `firehose.Firehose`) | Apache Kafka (via confluent-kafka producer) | Transport only — JSON payload identical |
| `EVERGREEN_FIREHOSE_NAME` stream | Kafka topic (configured via env var) | Topic replaces stream name |
| `LEGACY_FIREHOSE_NAME` stream | Kafka topic (configured via env var) or decommissioned | Evaluate if legacy stream is still needed |
| `DEBUG_*_FIREHOSE_NAME` streams | Kafka topic with debug prefix or feature-flagged | Debug routing preserved |
| `ThreadPoolExecutor` parallel send | async Kafka producer with batching | Delivery mechanism changes; output identical |

### Legacy Firehose Stream Routing

The legacy application routes events to up to four Firehose streams based on
environment variables:

| Stream | Env Var | Controlled By | Destination |
|---|---|---|---|
| Evergreen | `EVERGREEN_FIREHOSE_NAME` | `SEND_EVERGREEN=true` | S3 `cn-tvevents/<zoo>/tvevents/` |
| Legacy | `LEGACY_FIREHOSE_NAME` | `SEND_LEGACY=true` | S3 legacy bucket |
| Debug Evergreen | `DEBUG_EVERGREEN_FIREHOSE_NAME` | `TVEVENTS_DEBUG=true` | Debug S3 prefix |
| Debug Legacy | `DEBUG_LEGACY_FIREHOSE_NAME` | `TVEVENTS_DEBUG=true` | Debug S3 prefix |

### Target Kafka Topic Mapping

| Legacy Stream | Target Kafka Topic | Notes |
|---|---|---|
| Evergreen Firehose | Primary Kafka topic (configured via env var) | Main event delivery path |
| Legacy Firehose | Evaluate for decommission — may not need Kafka equivalent | Legacy stream may be obsolete |
| Debug Firehose streams | Debug Kafka topic or feature-flagged routing | Preserve debug capability |

### Event Output JSON Schema

The flattened JSON structure is the **output contract** — downstream consumers
depend on this exact schema. Both legacy (Firehose) and target (Kafka) must
produce identical JSON for the same input event.

#### Common Fields (all event types)

| Field | Type | Source | Transformation | Notes |
|---|---|---|---|---|
| `tvid` | string | `TvEvent.tvid` | Direct copy | TV unique identifier |
| `client` | string | `TvEvent.client` | Direct copy | Client identifier |
| `tvevent_timestamp` | number (ms) | `TvEvent.timestamp` | Renamed from `timestamp` | Event timestamp in milliseconds |
| `tvevent_eventtype` | string | `TvEvent.EventType` | Renamed from `EventType` | e.g. `ACR_TUNER_DATA`, `PLATFORM_TELEMETRY` |
| `zoo` | string | `FLASK_ENV` env var | Direct copy | Environment identifier (e.g. `tvevents-k8s`) |
| `namespace` | string | Event-type-specific handler | Derived per event type | Logical grouping |
| `appid` | string | Event-type-specific handler | Derived per event type | Application identifier |

#### ACR_TUNER_DATA Fields

| Field | Type | Source | Transformation | Notes |
|---|---|---|---|---|
| `channeldata_majorid` | number | `EventData.channelData.majorId` | Flattened from nested object | Channel major ID |
| `channeldata_minorid` | number | `EventData.channelData.minorId` | Flattened from nested object | Channel minor ID |
| `programdata_programid` | string | `EventData.programData.programId` | Flattened from nested object | Program identifier |
| `programdata_starttime` | number (ms) | `EventData.programData.startTime` | Converted to ms if value is in seconds | Program start time |
| `resolution_vres` | number | `EventData.resolution.vRes` | Flattened from nested object | Vertical resolution |
| `resolution_hres` | number | `EventData.resolution.hRes` | Flattened from nested object | Horizontal resolution |
| `eventtype` | string | Literal `"Heartbeat"` | Set if heartbeat event detected | Only present for heartbeat events |

#### PLATFORM_TELEMETRY Fields

| Field | Type | Source | Transformation | Notes |
|---|---|---|---|---|
| `paneldata_panelstate` | string | `EventData.PanelData.PanelState` | Uppercased (e.g. `"ON"`, `"OFF"`) | Panel power state |
| `paneldata_timestamp` | number | `EventData.PanelData.Timestamp` | Flattened from nested object | Panel event timestamp |
| `paneldata_wakeupreason` | number | `EventData.PanelData.WakeupReason` | Flattened from nested object | Wakeup reason code |

#### NATIVEAPP_TELEMETRY Fields

| Field | Type | Source | Transformation | Notes |
|---|---|---|---|---|
| `eventdata_timestamp` | number | `EventData.Timestamp` | Flattened from nested object | App event timestamp |

#### Obfuscation Fields (all event types when applicable)

| Field | Type | Source | Transformation | Notes |
|---|---|---|---|---|
| `channelid` | string or `"OBFUSCATED"` | `EventData.channelData.majorId` | Set to `"OBFUSCATED"` if channel is blacklisted or content is blocked | Obfuscation applied post-blacklist-check |
| `programid` | string or `"OBFUSCATED"` | `EventData.programData.programId` | Set to `"OBFUSCATED"` if channel is blacklisted or content is blocked | Obfuscation applied post-blacklist-check |
| `channelname` | string or `"OBFUSCATED"` | `EventData.channelData.channelName` | Set to `"OBFUSCATED"` if channel is blacklisted or content is blocked | Obfuscation applied post-blacklist-check |
| `iscontentblocked` | boolean | `EventData.iscontentblocked` | Direct copy | Triggers obfuscation when `true` |

#### Obfuscation Logic (must be preserved exactly)

```python
# Pseudocode — must match legacy behavior exactly
def should_obfuscate(channel_id: str, is_content_blocked: bool,
                     blacklisted_ids: set[str]) -> bool:
    return is_content_blocked or str(channel_id) in blacklisted_ids

def apply_obfuscation(output: dict) -> dict:
    if should_obfuscate(...):
        output["channelid"] = "OBFUSCATED"
        output["programid"] = "OBFUSCATED"
        output["channelname"] = "OBFUSCATED"
    return output
```

#### Example Output JSON (ACR_TUNER_DATA — non-obfuscated)

```json
{
  "tvid": "AE97B2F14A2C",
  "client": "smartcast",
  "tvevent_timestamp": 1709568000000,
  "tvevent_eventtype": "ACR_TUNER_DATA",
  "zoo": "tvevents-k8s",
  "namespace": "tuner",
  "appid": "acr",
  "channeldata_majorid": 704,
  "channeldata_minorid": 1,
  "programdata_programid": "EP038570790042",
  "programdata_starttime": 1709564400000,
  "resolution_vres": 1080,
  "resolution_hres": 1920,
  "channelid": "704",
  "programid": "EP038570790042",
  "channelname": "ESPN",
  "iscontentblocked": false
}
```

#### Example Output JSON (ACR_TUNER_DATA — obfuscated)

```json
{
  "tvid": "AE97B2F14A2C",
  "client": "smartcast",
  "tvevent_timestamp": 1709568000000,
  "tvevent_eventtype": "ACR_TUNER_DATA",
  "zoo": "tvevents-k8s",
  "namespace": "tuner",
  "appid": "acr",
  "channeldata_majorid": 704,
  "channeldata_minorid": 1,
  "programdata_programid": "EP038570790042",
  "programdata_starttime": 1709564400000,
  "resolution_vres": 1080,
  "resolution_hres": 1920,
  "channelid": "OBFUSCATED",
  "programid": "OBFUSCATED",
  "channelname": "OBFUSCATED",
  "iscontentblocked": false
}
```

## Environment Variables for Data Store Configuration

### Legacy

| Env Var | Purpose | Default (local dev) |
|---|---|---|
| `RDS_HOST` | PostgreSQL hostname | `localhost` |
| `RDS_DB` | PostgreSQL database name | `tvevents` |
| `RDS_USER` | PostgreSQL username | `tvevents` |
| `RDS_PASS` | PostgreSQL password | _(secrets manager)_ |
| `RDS_PORT` | PostgreSQL port | `5432` |
| `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` | File cache path | `/tmp/.blacklisted_channel_ids_cache` |
| `EVERGREEN_FIREHOSE_NAME` | Evergreen Firehose stream name | _(per environment)_ |
| `LEGACY_FIREHOSE_NAME` | Legacy Firehose stream name | _(per environment)_ |
| `DEBUG_EVERGREEN_FIREHOSE_NAME` | Debug evergreen Firehose stream | _(per environment)_ |
| `DEBUG_LEGACY_FIREHOSE_NAME` | Debug legacy Firehose stream | _(per environment)_ |
| `SEND_EVERGREEN` | Enable evergreen Firehose | `true` |
| `SEND_LEGACY` | Enable legacy Firehose | `true` |
| `TVEVENTS_DEBUG` | Enable debug Firehose streams | `false` |
| `FLASK_ENV` | Zoo identifier (used in output JSON as `zoo`) | `tvevents-k8s` |
| `T1_SALT` | HMAC salt for security hash validation | _(secrets manager)_ |
| `AWS_REGION` | AWS region for Firehose/RDS | `us-east-1` |

### Target

| Env Var | Purpose | Default (local dev) |
|---|---|---|
| `RDS_HOST` | PostgreSQL hostname (same RDS instance) | `localhost` |
| `RDS_DB` | PostgreSQL database name | `tvevents` |
| `RDS_USER` | PostgreSQL username | `tvevents` |
| `RDS_PASS` | PostgreSQL password | _(secrets manager)_ |
| `RDS_PORT` | PostgreSQL port | `5432` |
| `REDIS_HOST` | Redis hostname (new) | `localhost` |
| `REDIS_PORT` | Redis port (new) | `6379` |
| `REDIS_DB` | Redis database number (new) | `0` |
| `REDIS_PASSWORD` | Redis password (new) | _(secrets manager)_ |
| `BLACKLIST_CACHE_TTL` | Redis cache TTL in seconds (new) | `300` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses (new) | `localhost:9092` |
| `KAFKA_TOPIC` | Primary Kafka topic for events (new) | `tvevents` |
| `KAFKA_DEBUG_TOPIC` | Debug Kafka topic (new) | `tvevents-debug` |
| `KAFKA_SECURITY_PROTOCOL` | Kafka auth protocol (new) | `PLAINTEXT` |
| `ZOO` | Zoo identifier (replaces `FLASK_ENV`, used in output JSON) | `tvevents-k8s` |
| `T1_SALT` | HMAC salt for security hash validation (same) | _(secrets manager)_ |
| `AWS_REGION` | AWS region for RDS | `us-east-1` |

**Removed env vars (no longer needed):**
- `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` — replaced by Redis cache
- `EVERGREEN_FIREHOSE_NAME` — replaced by Kafka topic
- `LEGACY_FIREHOSE_NAME` — replaced by Kafka topic
- `DEBUG_*_FIREHOSE_NAME` — replaced by debug Kafka topic
- `SEND_EVERGREEN` / `SEND_LEGACY` — Kafka routing replaces Firehose routing
- `TVEVENTS_DEBUG` — replaced by `KAFKA_DEBUG_TOPIC` configuration
- `FLASK_ENV` — renamed to `ZOO` for clarity

## Migration Validation Checklist

- [ ] **RDS**: Target service connects to the same RDS instance and returns
      identical results for `SELECT DISTINCT channel_id FROM
      public.tvevents_blacklisted_station_channel_map`
- [ ] **Redis cache**: After cache population, `SMEMBERS
      tvevents:blacklisted_channels` matches the RDS query result set exactly
- [ ] **Redis TTL**: Cache key expires after 300 seconds and is repopulated on
      next request
- [ ] **Redis fallback**: When Redis is unreachable, service falls back to
      in-memory cache populated from RDS
- [ ] **Kafka output format**: JSON records produced to Kafka are
      byte-compatible with legacy Firehose records for the same input event
- [ ] **Obfuscation**: Blacklisted channel IDs produce `"OBFUSCATED"` values
      in `channelid`, `programid`, and `channelname` — identical to legacy
- [ ] **Field naming**: All output JSON field names match legacy exactly
      (lowercase, underscore-separated, no schema drift)
- [ ] **Timestamp conversion**: `programdata_starttime` correctly converts
      seconds to milliseconds when the source value is in seconds
- [ ] **PanelState casing**: `paneldata_panelstate` is always uppercased
- [ ] **Heartbeat marker**: `eventtype: "Heartbeat"` is present only for
      heartbeat events

## Reconciliation Queries

### Blacklist Cache Reconciliation

| Check | Method | Expected Result |
|---|---|---|
| RDS row count | `SELECT COUNT(DISTINCT channel_id) FROM public.tvevents_blacklisted_station_channel_map;` | Row count > 0 |
| Redis set cardinality | `SCARD tvevents:blacklisted_channels` | Matches RDS `COUNT(DISTINCT channel_id)` |
| Full set comparison | `SMEMBERS tvevents:blacklisted_channels` vs. `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map;` | Identical sets — every ID in RDS is in Redis and vice versa |
| Cache TTL active | `TTL tvevents:blacklisted_channels` | Returns value between 1 and 300 (seconds remaining) |
| Cache repopulation | Wait for TTL expiry → send a request → `SCARD tvevents:blacklisted_channels` | Repopulated with correct count |
| Membership spot-check | Pick a known blacklisted channel ID → `SISMEMBER tvevents:blacklisted_channels {id}` | Returns `1` (true) |
| Non-member spot-check | Pick a known non-blacklisted channel ID → `SISMEMBER tvevents:blacklisted_channels {id}` | Returns `0` (false) |

### Event Output Format Reconciliation

| Check | Method | Expected Result |
|---|---|---|
| Schema comparison | Send identical input to legacy and target services → capture Firehose record and Kafka record → JSON diff | 0 field differences — identical key names, types, and values |
| ACR_TUNER_DATA output | Send ACR event payload → capture Kafka output → verify all `channeldata_*`, `programdata_*`, `resolution_*` fields present | All fields present with correct types |
| PLATFORM_TELEMETRY output | Send platform event payload → capture Kafka output → verify `paneldata_*` fields present and `paneldata_panelstate` is uppercased | Fields present, PanelState uppercased |
| NATIVEAPP_TELEMETRY output | Send native app event payload → capture Kafka output → verify `eventdata_timestamp` present | Field present with correct type |
| Obfuscation (blacklisted) | Send event with blacklisted `majorId` → capture Kafka output | `channelid`, `programid`, `channelname` all equal `"OBFUSCATED"` |
| Obfuscation (content blocked) | Send event with `iscontentblocked: true` → capture Kafka output | `channelid`, `programid`, `channelname` all equal `"OBFUSCATED"` |
| Obfuscation (not triggered) | Send event with non-blacklisted channel and `iscontentblocked: false` | `channelid`, `programid`, `channelname` contain original values |
| Heartbeat marker | Send heartbeat ACR event → capture Kafka output | `eventtype` field equals `"Heartbeat"` |
| Non-heartbeat | Send non-heartbeat ACR event → capture Kafka output | `eventtype` field absent or not `"Heartbeat"` |
| Timestamp conversion | Send ACR event with `startTime` in seconds (10-digit value) | `programdata_starttime` in output is in milliseconds (13-digit value) |
| Batch volume test | Send 1,000 events → count Kafka records produced | 1,000 records (1:1 input-to-output ratio) |

### Cross-System Reconciliation (Phase 2 Parallel Run)

| Check | Method | Expected Result |
|---|---|---|
| Blacklist sync | Compare legacy file cache content with `SMEMBERS tvevents:blacklisted_channels` | Identical channel ID sets |
| Output format parity | Replay 100 captured production payloads through both services → diff outputs | 0 differences in JSON schema or values |
| Obfuscation parity | Replay payloads containing blacklisted channels through both services → diff | Same fields obfuscated with `"OBFUSCATED"` |
| Throughput parity | Monitor Kafka producer metrics vs. legacy Firehose CloudWatch `IncomingRecords` during traffic split | Within ±1% record count for equivalent traffic volume |

## Edge Cases

- **Empty blacklist table**: If the RDS table has zero rows, the Redis SET is
  not created (no `SADD` with zero members). `EXISTS` returns `0`, and the
  service treats all channels as non-blacklisted. This matches legacy behavior
  where an empty file cache means no channels are blacklisted.

- **Redis SET vs. file format**: The legacy file cache stores channel IDs as
  newline-delimited strings in a flat file. The target stores them as Redis SET
  members. The data content is identical (set of channel ID strings) — only the
  storage format changes.

- **Channel ID type coercion**: Legacy code converts `majorId` (which may be
  numeric) to a string for blacklist comparison: `str(channel_id) in
  blacklisted_ids`. The target must preserve this string coercion to avoid
  type-mismatch false negatives.

- **Obfuscation trigger precedence**: Obfuscation triggers if **either**
  `iscontentblocked` is `true` **or** the channel ID is in the blacklist. Both
  conditions are OR'd — not AND'd. The target must preserve this logic exactly.

- **`programdata_starttime` unit detection**: Legacy code detects whether
  `startTime` is in seconds (10-digit) or milliseconds (13-digit) and converts
  to milliseconds if needed. The target must use the same heuristic (e.g.,
  `if startTime < 10_000_000_000: startTime *= 1000`).

- **`paneldata_panelstate` casing**: Legacy code calls `.upper()` on
  `PanelState`. The target must do the same — values like `"on"` must become
  `"ON"` in the output.

- **Heartbeat detection**: The `eventtype: "Heartbeat"` field is only added for
  heartbeat events within ACR_TUNER_DATA. It is not a rename of `EventType` —
  it is a separate field added conditionally. The target must replicate this
  conditional inclusion.

- **Null/missing EventData fields**: If nested fields (e.g.,
  `channelData.majorId`) are missing from the input `EventData`, the legacy
  code may omit the corresponding output field or set it to `None`. The target
  must handle missing nested fields identically — do not substitute default
  values that the legacy code does not produce.

- **`zoo` field source change**: Legacy reads `FLASK_ENV`; target reads `ZOO`.
  Both must produce the same string value in the output JSON `zoo` field for a
  given environment. Verify that `ZOO` env var is set to the same value as the
  legacy `FLASK_ENV` during parallel run.

- **Kafka ordering vs. Firehose ordering**: Kinesis Firehose does not guarantee
  ordering. Kafka partitions provide per-partition ordering. Downstream
  consumers should not assume ordering changed — the output contract is
  unordered event delivery, same as legacy.

- **Redis connection failure during cache population**: If Redis is unavailable
  when the cache TTL expires, the service must still function by querying RDS
  directly and caching in-memory. The next request after Redis recovers should
  repopulate the Redis SET. No request should fail due to Redis unavailability.
