# ADR 006: Use Terraform for Infrastructure-as-Code

## Status
Accepted

## Context
The legacy service uses Helm charts for Kubernetes deployment but has no infrastructure-as-code for cloud resources. AWS infrastructure (RDS instances, IAM roles, security groups, etc.) is managed partially through manual processes and partially through ad-hoc scripts. This makes environment reproduction unreliable, auditing difficult, and disaster recovery slow.

## Decision
Use **Terraform** for provisioning and managing AWS infrastructure (EKS service definitions, Kafka topics, Redis/ElastiCache clusters, RDS access policies, IAM roles, security groups). Use **Helm** for Kubernetes resource templates (Deployments, Services, ConfigMaps, etc.).

## Alternatives Considered
- **Keep Helm-only** — Rejected. Helm manages Kubernetes resources but cannot provision cloud infrastructure (RDS instances, IAM roles, VPC configuration). The gap between "Kubernetes resources exist" and "cloud resources exist" would remain manually managed.
- **AWS CDK / CloudFormation** — Rejected. CloudFormation is AWS-specific, limiting portability. CDK generates CloudFormation under the hood and adds a code generation layer. The team has more experience with Terraform's declarative HCL syntax.
- **Pulumi** — Rejected. Pulumi uses general-purpose programming languages for infrastructure, which appeals to some teams. However, the team has existing Terraform experience and the organization has Terraform modules and patterns already in use.

## Consequences
- **Reproducible infrastructure** — Any environment (dev, staging, prod) can be created or destroyed with `terraform apply` using the appropriate variable file. No manual steps required.
- **State tracking** — Terraform state is stored in an S3 backend with DynamoDB locking, providing a single source of truth for what infrastructure exists.
- **Auditability** — All infrastructure changes go through code review (Terraform plan in PR) before apply.
- **Trade-off: learning curve** — Team members unfamiliar with Terraform will need onboarding. HCL syntax and Terraform's plan/apply workflow have a learning curve, though the organization has internal resources and modules to accelerate this.
