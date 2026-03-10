# ADR 002: Use Apache Kafka (AWS MSK) for Event Delivery

## Status

Accepted

## Context

The legacy tvevents-k8s service delivers processed TV event data to AWS Kinesis Data Firehose streams via the `cnlib.firehose.Firehose` class (boto3 SDK). The platform is migrating from Kinesis Data Firehose to Apache Kafka (AWS MSK). The Firehose integration is tightly coupled through the cnlib git submodule, which is being eliminated. The user explicitly requires Kafka to replace Firehose.

## Decision

Replace AWS Kinesis Data Firehose with Apache Kafka (AWS MSK) for event delivery. Create a standalone `rebuilder-kafka-module` Python package with a `KafkaProducerClient` class using `confluent-kafka` with SASL/SCRAM authentication. Map the four legacy Firehose stream names to Kafka topic names via environment variables.

## Alternatives Considered

- **Keep Kinesis Data Firehose** — Rejected. Platform mandate to migrate to Kafka. Firehose is tightly coupled through cnlib which is being eliminated.
- **AWS SQS** — Rejected. SQS is a queue, not a streaming platform. Does not provide the same delivery semantics or downstream consumer model as Kafka.
- **AWS Kinesis Data Streams** — Rejected. Still AWS-specific. Kafka provides a more portable, industry-standard streaming interface.

## Consequences

- **Positive:** Aligns with platform migration mandate. Eliminates cnlib Firehose dependency. Kafka provides at-least-once delivery with acknowledgment. Standalone module is reusable across services.
- **Negative:** Downstream pipeline consumers must be configured for Kafka before cutover. SASL/SCRAM credential management adds operational complexity. Kafka delivery semantics differ from Firehose buffered batch.
- **Mitigation:** Parallel deployment — run both services simultaneously during transition. Coordinate with downstream pipeline team for Kafka consumer setup.
