# ADR 007: API Versioning — Deferred

## Status

Accepted

## Context

The legacy evergreen-tvevents service exposes a single primary endpoint at the root path (`POST /`). SmartCast TV devices — millions of deployed units with immutable firmware — send telemetry events to this endpoint. The firmware cannot be updated to point at a new path, meaning any change to the root endpoint URL would silently break the entire device fleet's telemetry pipeline.

The full set of inbound consumers is not documented. Beyond the SmartCast TV fleet, there may be other internal systems, test harnesses, or third-party integrations that POST to the root path. Without a complete consumer inventory, any API path change carries unknown risk.

The feasibility assessment flagged API versioning as a Caution item, recommending deferral until a consumer inventory is completed. The assessment noted that introducing versioning prematurely (e.g., moving the endpoint to `/v1/`) could break unknown consumers with no rollback path for firmware-embedded clients.

## Decision

Defer API versioning. The rebuilt service will preserve the root path `POST /` exactly as the legacy service exposes it. No version prefix, content-type versioning, or header-based versioning will be introduced in the initial rebuild phases.

API versioning will be evaluated in Phase 3, contingent on completion of a consumer inventory that documents all inbound clients, their URL expectations, and their update capabilities. The versioning strategy (path-based, header-based, or content-type-based) will be selected based on the inventory findings.

## Alternatives Considered

**Add `/v1` path prefix immediately.** This is the conventional REST API versioning approach: mount the current API at `/v1/` and redirect or alias the root path. However, SmartCast firmware cannot be updated to send requests to `/v1/`, meaning the root path must continue to work regardless. Adding a prefix now provides no benefit (there is only one version) while creating a maintenance burden (two paths serving identical logic). Rejected for Phase 1; may be revisited in Phase 3.

**Content-type versioning (Accept header).** Version selection through the `Accept` header (e.g., `application/vnd.tvevents.v1+json`) is transparent to URL routing but requires all consumers to send the correct header. SmartCast firmware sends a fixed content type; changing it is not possible. Without a consumer inventory, requiring header-based versioning risks breaking unknown clients. Rejected for Phase 1.

**Never version the API.** Committing to never versioning the API is premature. The consumer inventory may reveal that versioning is necessary — for example, if there are updatable consumers that would benefit from a versioned contract while legacy firmware clients continue to use the root path. Keeping the option open costs nothing. Rejected as a permanent stance.

## Consequences

**Positive:**
- Zero risk of breaking unknown consumers. The root path `POST /` continues to work exactly as before.
- Simpler initial implementation: no routing complexity for version negotiation, no path aliasing, no header parsing for version selection.
- Preserves flexibility: the versioning strategy can be tailored to the actual consumer landscape once the inventory is complete.

**Negative:**
- Possible technical debt if versioning is needed later. Adding versioning after the fact is more complex than building it in from the start (existing clients expect the root path, so backward compatibility must be maintained regardless).
- Phase 3 dependency on consumer inventory completion: if the inventory is delayed or deprioritized, the versioning decision remains unresolved indefinitely.
- Without versioning, breaking changes to the API contract (request schema, response format, error codes) must be made in a backward-compatible manner, constraining future evolution.
