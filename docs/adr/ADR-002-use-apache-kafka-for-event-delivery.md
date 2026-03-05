# ADR 002: Use Apache Kafka for Event Delivery

## Status
Accepted

## Context
The legacy service delivers TV events to AWS Kinesis Firehose through the `cnlib` shared library. This creates two problems: a hard dependency on the `cnlib` package (which is being decommissioned) and vendor lock-in to AWS Kinesis Firehose for event streaming. The organization has standardized on Apache Kafka as the event streaming platform, and other teams are actively migrating off Firehose.

## Decision
Use **Apache Kafka** for event delivery, accessed via the **`confluent-kafka`** Python client library.

## Alternatives Considered
- **Keep Kinesis Firehose** — Rejected. The organization has mandated migration away from Firehose to Kafka. Continuing with Firehose would diverge from the platform direction and maintain the `cnlib` dependency.
- **AWS MSK + custom producer** — Rejected. MSK is managed Kafka, and `confluent-kafka` is the standard Python client for Kafka regardless of the broker deployment. There is no benefit to writing a custom producer when the standard client exists.
- **Apache Pulsar** — Rejected. No organizational infrastructure exists for Pulsar. Adopting it would require provisioning and operating a new streaming platform with no team experience.

## Consequences
- **Removes AWS Firehose dependency** — The service no longer depends on `cnlib` for event delivery or on Kinesis Firehose as a managed service.
- **Aligns with organizational direction** — Uses the same event streaming platform that other teams are adopting, enabling cross-team event consumption and tooling reuse.
- **Trade-off: Kafka infrastructure** — Requires a running Kafka cluster (AWS MSK in production, local broker for development). The infrastructure team manages MSK, but the service team owns topic configuration.
- **Trade-off: native library dependency** — `confluent-kafka` depends on `librdkafka`, a C library. This requires the native library to be available in the container image and may complicate local development on some platforms.
