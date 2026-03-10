# Feasibility Analysis

## Opportunity 1: Replace Flask with FastAPI

**Impact:** High

| Dimension | Assessment |
|---|---|
| **Effort** | **M** — FastAPI route definitions are structurally similar to Flask. Main work is defining Pydantic models for TvEvent/EventData payloads and converting middleware/error handlers. ~1,169 lines of app code to port. |
| **Risk** | **Medium** — Payload backward compatibility is the primary risk. Pydantic strict validation may reject payloads that Flask accepted silently. Must test with production-representative payloads. Performance at scale (100-200 pods) needs verification. |
| **Dependencies** | Blocks Opportunity 4 (/ops/* endpoints benefit from Pydantic models). Independent of Opportunities 2 and 3. |
| **Rollback** | Revert to legacy Flask service — legacy repo remains unmodified. |

**Verdict: Go** — User explicitly requires FastAPI. Risk is manageable with thorough payload testing.

---

## Opportunity 2: Replace Kinesis Data Firehose with Apache Kafka (AWS MSK)

**Impact:** Critical

| Dimension | Assessment |
|---|---|
| **Effort** | **M** — Create standalone Kafka module, replace `send_to_valid_firehoses()` with `send_to_valid_topics()`, map stream names to topic names. Core delivery logic is similar (send JSON to a destination). |
| **Risk** | **Medium** — Downstream pipeline readiness is the primary risk. Kafka delivery semantics (at-least-once with acknowledgment) differ from Firehose (buffered batch). SASL/SCRAM credential management adds operational complexity. Must coordinate topic creation and consumer setup. |
| **Dependencies** | Depends on Opportunity 3 (cnlib elimination — Firehose client lives in cnlib). Blocked by downstream pipeline team readiness for Kafka consumers. |
| **Rollback** | Parallel deployment — run both services simultaneously. Roll back by shifting traffic to legacy service. |

**Verdict: Go** — Required by platform migration mandate. Downstream coordination is an operational concern, not a technical blocker for the rebuild.

---

## Opportunity 3: Eliminate cnlib Git Submodule Dependency

**Impact:** High

| Dimension | Assessment |
|---|---|
| **Effort** | **S** — Only 3 functions to replace: `firehose.Firehose` (replaced by Kafka module), `token_hash.security_hash_match` (inline ~20 lines with `hmac.compare_digest()`), `log.getLogger` (standard `logging.getLogger()`). |
| **Risk** | **Low** — Hash algorithm must produce identical output for backward compatibility. Test with known tvid/salt/hash triples from production. Logging change is trivial. |
| **Dependencies** | Opportunity 2 (Kafka) replaces the Firehose function. Security hash and logging replacements are independent. |
| **Rollback** | Hash validation can be tested in isolation. If inline security module produces wrong hashes, fix is a single-file change. |

**Verdict: Go** — Low effort, low risk, high value. Eliminates the primary architectural pain point.

---

## Opportunity 4: Add /ops/* Diagnostic and Remediation Endpoints

**Impact:** High

| Dimension | Assessment |
|---|---|
| **Effort** | **M** — 11 endpoints to implement. Most are read-only introspection (config, dependencies, errors, metrics). Drain and cache flush require application state management. Golden Signals and RED metrics require metric collection middleware. |
| **Risk** | **Low** — Additive change — does not modify existing ingestion logic. Endpoints are independent of the POST / flow. |
| **Dependencies** | Benefits from Opportunity 1 (FastAPI Pydantic models for responses). Independent of Opportunities 2 and 3. |
| **Rollback** | Endpoints can be removed without affecting core functionality. |

**Verdict: Go** — Required by service bootstrap standards. Low risk, clear deliverables.

---

## Opportunity 5: OTEL Auto-Instrumentation

**Impact:** Medium

| Dimension | Assessment |
|---|---|
| **Effort** | **S** — Primarily configuration: add `opentelemetry-instrument` to entrypoint, remove manual instrumentor calls. Retain manual spans for business logic tracing. |
| **Risk** | **Low** — OTEL auto-instrumentation is mature and well-documented. FastAPI instrumentation package (`opentelemetry-instrumentation-fastapi`) exists. Fallback: revert to manual instrumentation. |
| **Dependencies** | Depends on Opportunity 1 (FastAPI) — auto-instrumentation package differs for FastAPI vs Flask. |
| **Rollback** | Switch back to manual instrumentation — code changes only, no data loss. |

**Verdict: Go** — User explicitly requires OTEL auto-instrumentation. Low effort, low risk.

---

## Opportunity 6: Align Operational Files with Template Repo Patterns

**Impact:** Medium

| Dimension | Assessment |
|---|---|
| **Effort** | **M** — Dockerfile, entrypoint.sh, environment-check.sh are moderate rewrites. Helm chart migration to template chart templates is the largest piece (18 template files to adapt). pip-compile setup is straightforward. |
| **Risk** | **Medium** — Helm chart migration requires careful values.yaml mapping. Template chart templates may not cover all tvevents-specific configurations (scaling policies, pod identity). |
| **Dependencies** | Independent of Opportunities 1-5. Can be done in parallel with application code. |
| **Rollback** | Operational files can be iterated independently of application code. |

**Verdict: Go** — Required by user instructions to follow template repo patterns. Helm chart migration is the main effort.

---

## Opportunity 7: Create Standalone RDS Python Module

**Impact:** Medium

| Dimension | Assessment |
|---|---|
| **Effort** | **S** — `RdsClient` class with connection pool, retry, health check. The existing `TvEventsRds` provides the interface blueprint. |
| **Risk** | **Low** — PostgreSQL client libraries are mature. Connection pooling is well-understood. Module can be tested independently. |
| **Dependencies** | Independent — can be built before or after application code. Application dbhelper will consume the module. |
| **Rollback** | Fall back to direct psycopg2 connection (current approach). |

**Verdict: Go** — User explicitly requires standalone RDS module. Low effort, clear value.

---

## Opportunity 8: Add Comprehensive Quality Gates

**Impact:** Medium

| Dimension | Assessment |
|---|---|
| **Effort** | **S** — Tool configuration in `pyproject.toml` and CI workflow. ruff, mypy, pytest-cov, pip-audit are all standard Python tooling. |
| **Risk** | **Low** — Quality gates are additive. If mypy strict mode creates too much friction, can relax to basic mode. |
| **Dependencies** | Should be set up early so all code is written to pass gates from the start. |
| **Rollback** | Quality gate configurations can be adjusted without application changes. |

**Verdict: Go** — Required by service bootstrap standards. Set up before writing application code.

---

## Summary

| Opportunity | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|
| 1. FastAPI | High | M | Medium | **Go** |
| 2. Kafka for Firehose | Critical | M | Medium | **Go** |
| 3. Eliminate cnlib | High | S | Low | **Go** |
| 4. /ops/* Endpoints | High | M | Low | **Go** |
| 5. OTEL Auto-Instrumentation | Medium | S | Low | **Go** |
| 6. Template Repo Alignment | Medium | M | Medium | **Go** |
| 7. Standalone RDS Module | Medium | S | Low | **Go** |
| 8. Quality Gates | Medium | S | Low | **Go** |

**All opportunities are Go.** They form a coherent rebuild — each addresses a documented pain point, the user has explicitly requested several, and the combined effort is appropriate for a full-service rebuild.

**Execution order:**
1. Quality gates (Opportunity 8) — set up first so all code passes from the start
2. Standalone modules (Opportunities 7, 3) — RDS module, security hash inline
3. FastAPI service (Opportunity 1) — core application with Pydantic models
4. Kafka integration (Opportunity 2) — standalone Kafka module + delivery logic
5. /ops/* endpoints (Opportunity 4) — SRE diagnostic and remediation
6. OTEL auto-instrumentation (Opportunity 5) — entrypoint configuration
7. Template repo alignment (Opportunity 6) — Dockerfile, entrypoint, Helm, pip-compile
