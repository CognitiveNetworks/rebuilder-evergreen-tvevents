# ADR 002: Delivery Infrastructure — Kafka over Firehose

## Status

Accepted

## Context

The legacy evergreen-tvevents service delivers classified TV telemetry events to up to six AWS Kinesis Firehose streams. Delivery is performed through `cnlib.firehose.Firehose`, a vendored library symlinked from the `cntools_py3` directory. Each event type maps to a specific Firehose delivery stream, and the service constructs delivery payloads with metadata before dispatching.

This architecture creates tight coupling to AWS at multiple levels: the delivery transport (Kinesis Firehose), the client library (cnlib.firehose), and the downstream storage (Firehose → S3/Redshift). The cnlib symlink model means the delivery code is not independently versioned, not independently testable, and shares a deployment lifecycle with the service itself. Any change to cnlib.firehose affects all services consuming it simultaneously.

The modernization assessment identified Firehose replacement as a Go decision, noting that cloud-agnostic delivery infrastructure is a strategic goal across the rebuilt service fleet. Multiple rebuilt services will need event delivery capabilities, making a shared standalone module the efficient path.

The project constraints specify that Kafka should replace Firehose, implemented as a standalone Python module published as a pip package — not vendored or symlinked into the service repository.

## Decision

Replace AWS Kinesis Firehose with Apache Kafka for all event delivery. Implement the Kafka producer as a standalone Python module, published as an independently versioned pip package. The service will declare this module as a dependency in `pyproject.toml` and consume it through a clean interface.

The standalone Kafka module will provide: topic-based delivery (mapping legacy stream names to Kafka topics), serialization, delivery confirmation, OTEL instrumentation for producer spans, and health check support. The module's interface will be designed for reuse across multiple rebuilt services.

The legacy cnlib.firehose dependency will be dropped entirely. cnlib will be retained only for `token_hash` and `log` functionality.

## Alternatives Considered

**Keep AWS Kinesis Firehose.** This would eliminate migration effort for the delivery layer but perpetuates vendor lock-in to AWS. The cnlib.firehose symlink model would remain, with its associated fragility and testing difficulties. Firehose's batch-oriented delivery semantics are also less flexible than Kafka's topic-based pub/sub model. Rejected.

**AWS MSK with a Firehose compatibility adapter.** Managed Streaming for Apache Kafka (MSK) provides Kafka on AWS, and an adapter could translate Firehose API calls to Kafka producer calls. This adds an unnecessary translation layer and still ties the deployment to AWS-managed infrastructure at the API level. Rejected.

**Apache Pulsar.** Pulsar offers similar pub/sub semantics with built-in multi-tenancy and geo-replication. However, the team has no Pulsar operational experience, the ecosystem tooling is less mature than Kafka's, and the client library landscape for Python is narrower. Kafka's ecosystem maturity and team familiarity make it the pragmatic choice. Rejected.

**Direct S3 delivery (bypassing streaming).** Writing events directly to S3 would simplify the delivery path but loses streaming semantics entirely. Downstream analytics consumers that depend on near-real-time event availability would be broken. The shift from streaming to batch delivery is a fundamental architectural change that downstream teams have not agreed to. Rejected.

## Consequences

**Positive:**
- Cloud-agnostic delivery infrastructure eliminates AWS vendor lock-in for the event pipeline.
- Clean module boundary with independent versioning enables the Kafka module to evolve on its own release cycle.
- Reusable across multiple rebuilt services, avoiding per-service delivery code duplication.
- Kafka's topic-based model provides more flexible routing than Firehose's fixed stream mapping.
- OTEL instrumentation in the module provides delivery-layer observability without per-service boilerplate.

**Negative:**
- Kafka cluster infrastructure must be provisioned and operated (or a managed Kafka service procured).
- Team requires Kafka producer expertise — configuration tuning (acks, retries, batch size, linger) affects delivery guarantees.
- All downstream consumers currently reading from Firehose delivery targets (S3, Redshift) must migrate to consuming from Kafka topics. This is a cross-team coordination dependency.
- An additional pip package must be maintained, versioned, and published — adding overhead to the dependency supply chain.
