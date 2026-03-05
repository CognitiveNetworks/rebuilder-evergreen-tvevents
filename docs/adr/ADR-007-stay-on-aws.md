# ADR 007: Stay on AWS

## Status
Accepted

## Context
The evergreen-tvevents service currently runs on AWS infrastructure: EKS for container orchestration, RDS for PostgreSQL, and Kinesis Firehose for event streaming. There is no organizational mandate to migrate to a different cloud provider. The existing AWS account has established VPC networking, IAM policies, security groups, and monitoring integrations.

## Decision
**Stay on AWS.** Use EKS for container orchestration, RDS for PostgreSQL, ElastiCache for Redis, and MSK for managed Kafka.

## Alternatives Considered
- **Migrate to GCP** — Rejected. There is no business requirement driving a cloud migration. Moving to GCP would introduce significant migration complexity (networking, IAM, service equivalents) without a corresponding benefit.
- **Multi-cloud deployment** — Rejected. Running the service across multiple cloud providers would add operational complexity (multiple IAM systems, networking configurations, monitoring integrations) without a demonstrated need for provider redundancy at this service level.

## Consequences
- **No cloud migration overhead** — The rebuild focuses on application modernization without the additional scope of a cloud provider migration.
- **Existing infrastructure reuse** — The service continues to use the established VPC, subnets, security groups, and IAM structure. Networking and access control do not need to be redesigned.
- **Modernization within AWS** — Kafka (MSK) replaces Kinesis Firehose, and ElastiCache (Redis) replaces file-based caching. These are modernization steps that stay within the AWS ecosystem.
