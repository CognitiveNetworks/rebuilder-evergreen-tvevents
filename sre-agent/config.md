# SRE Agent Configuration

**Instructions:** Fill out this file when setting up the SRE agent for a specific project. This provides the agent with the service registry, thresholds, and escalation contacts it needs to operate.

## Service Registry

> List every service the agent monitors. The agent uses these base URLs to call `/ops/*` endpoints.
>
> **Populating URLs:** Service names are pre-filled during the rebuild process (Step 7). Base URLs are populated after infrastructure is provisioned — typically after `terraform apply` outputs the Cloud Run or load balancer URL. Before wiring alerting, verify each URL responds:
> ```bash
> curl <base-url>/ops/status | jq   # Should return {"status": "healthy", ...}
> curl <base-url>/ops/health | jq   # Should show all dependencies healthy
> ```

| Service Name | Base URL | Environment | Critical? | Notes |
|---|---|---|---|---|
| evergreen-tvevents | *[TODO: URL after infra provisioning]* | dev | yes | TV telemetry ingestion service |
| evergreen-tvevents | *[TODO: URL after infra provisioning]* | staging | yes | TV telemetry ingestion service |
| evergreen-tvevents | *[TODO: URL after infra provisioning]* | prod | yes | TV telemetry ingestion service |

## Tech Stack

> Populated from the chosen rebuild candidate. The agent uses this to make stack-aware decisions.

- **Cloud Provider:** AWS
- **Orchestration:** Kubernetes (EKS) with KEDA autoscaling
- **Backend:** Python 3.12 / FastAPI
- **Database:** PostgreSQL RDS (read-only blacklist table via standalone RDS module)
- **Cache:** File-based JSON cache (3-tier: memory → file → RDS)
- **Database networking:** *[TODO: private IP only / public IP / cross-cloud]* <!-- TODO: fill after infra provisioning -->
- **Additional Services:** Apache Kafka (event delivery via standalone Kafka module), cnlib (token_hash, log)

## Alert Source

> The SRE agent receives alerts from your monitoring/alerting platform (GCP Cloud Monitoring, New Relic, Datadog, etc.) — not from PagerDuty. PagerDuty is used only for escalation when the agent cannot resolve an issue.

- **Alerting Platform:** *[TODO: New Relic, Datadog, or CloudWatch — confirm alerting platform]* <!-- TODO: fill after infra provisioning -->
- **Webhook Endpoint:** `<sre-agent-url>/webhook/alerts?auth_token=<ops-auth-token>`
- **Alert Routing:** *[TODO: describe how alerts flow — e.g., CloudWatch Alarm → SNS → webhook → SRE agent → diagnose → escalate to PagerDuty if unresolved]* <!-- TODO: fill after infra provisioning -->

## PagerDuty Escalation

> PagerDuty is the escalation target. The agent creates PagerDuty incidents only when it cannot resolve an issue and needs a human. Populated after PagerDuty setup.

- **API Token:** *[stored in secrets manager — reference only, not the actual token]*
- **Escalation Policy ID:** *[PagerDuty escalation policy for human handoff]*
- **Service ID:** *[PagerDuty service ID — find in URL: `https://<domain>.pagerduty.com/services/PXXXXXX`]*
- **Routing Key (Events API v2):** *[integration key from PagerDuty service → Integrations → Events API v2 — used by SRE agent to CREATE incidents on escalation]*

## SLO Thresholds

> Per-service SLO targets. The agent uses these to evaluate `/ops/status` verdicts and determine severity.

| Service | Availability SLO | Latency SLO (p99) | Error Rate SLO | Error Budget (monthly) |
|---|---|---|---|---|
| evergreen-tvevents | 99.9% | < 200ms | < 0.1% | 43.2 min/month |

## Escalation Contacts

| Priority | Contact | Channel |
|---|---|---|
| P1 — Critical | [On-call engineer] | [PagerDuty + Slack channel] |
| P2 — High | [On-call engineer] | [PagerDuty + Slack channel] |
| P3 — Medium | [Team lead] | [Slack channel] |
| P4 — Low | [Team queue] | [GitHub issue] |

## Scaling Limits

> Per-service scaling bounds. The SRE agent can only scale services that appear in this table, and only within the configured min/max range. Services without an entry here cannot be scaled by the agent — saturation alerts for those services will be escalated.

| Service Name | Min Instances | Max Instances | Scaling Mode | Notes |
|---|---|---|---|---|
| evergreen-tvevents | 1 | 500 | cloud_native | KEDA ScaledObject on EKS; triggers TBD |

### Scaling Modes

- **application** — the service manages its own scaling. The agent calls `POST /ops/scale` on the service with `{"target_instances": N, "reason": "..."}`. The service is responsible for adjusting its own instance count.
- **cloud_native** — the agent adjusts the replica/instance count directly via cloud provider APIs (GKE HPA, Cloud Run instance count, ECS desired count). Requires write IAM permissions (see Cloud Platform Access below).

### Scaling Safety

- The agent always uses absolute targets, never relative increments.
- The agent never scales below min or above max.
- If the service is already at max and still saturated, the agent escalates for capacity planning.
- Scaling is a remediation action, not a substitute for root cause analysis. If saturation is caused by a leak or runaway process, scaling will not fix it.

## Agent Auth

> The `ops-auth-token` is the bearer token the SRE agent sends in the `Authorization` header when calling `/ops/*` endpoints on monitored services. If using `deploy.sh`, this token is auto-generated and stored in AWS Secrets Manager. For manual setup, generate a random token, store it in your secrets manager, and configure both the SRE agent (`OPS_AUTH_TOKEN` env var) and the monitored service to use it.

- **Service Account:** [SRE agent service account with scoped permissions for `/ops/*` endpoints only]
- **Auth Method:** [Bearer token / mTLS / IAM — reference to secrets manager entry]
- **Permissions:** Read-only diagnostics + safe remediation. No write access to application data, infrastructure, or deployments.

## Cloud Platform Access

> The SRE agent requires read-only access to cloud provider APIs for diagnostic correlation. It uses this to understand managed service health alongside the `/ops/*` application endpoints. The agent never modifies cloud infrastructure.

> **Template instruction:** Keep only the section that matches your cloud provider. Delete the other section entirely — leftover cloud-provider sections create noise that can mislead the SRE agent about which cloud it is operating in.

### AWS
- **Required Policies (diagnostics — read-only):**
  - `CloudWatchReadOnlyAccess` — read metrics and alarms
  - `CloudWatchLogsReadOnlyAccess` — query logs
  - `AmazonRDSReadOnlyAccess` — database instance status and metrics
  - `AmazonElastiCacheReadOnlyAccess` — cache cluster status
  - `AmazonEKSReadOnlyAccess` — EKS cluster and node group status
  - `AmazonEC2ReadOnlyAccess` — instance and network status
  - `AmazonSQSReadOnlyAccess` — queue depth and metrics (if applicable)
- **Required Policies (scaling — only if using cloud_native scaling mode):**
  - Custom policy with `eks` pod scaling permissions — update EKS deployment replicas
  - Note: Scope these policies with resource-level conditions to only the specific services the agent is allowed to scale

## Runtime Configuration

> The SRE agent runs as a containerized service. See `runtime/README.md` for full setup and deployment instructions.

### Required Environment Variables

| Variable | Source | Description |
|---|---|---|
| `LLM_API_KEY` | Secrets manager | LLM API key (GitHub PAT for GitHub Models, OpenAI key, etc.). |
| `PAGERDUTY_API_TOKEN` | Secrets manager | PagerDuty API token for creating incidents on escalation |
| `OPS_AUTH_TOKEN` | Secrets manager | Bearer token the agent uses to authenticate against `/ops/*` endpoints |
| `SERVICE_REGISTRY` | Config / env | Comma-separated service list: `name\|url\|critical` (e.g., `evergreen-tvevents\|https://tvevents.example.com\|true`) |

### Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `gpt-4o` | LLM model ID |
| `LLM_MODEL_ESCALATION` | (empty) | Stronger model for complex incidents. If set, the agent starts with `LLM_MODEL` and switches to this after `LLM_ESCALATION_TURN` turns without resolution. |
| `LLM_ESCALATION_TURN` | `5` | Turn number at which to switch to the escalation model. Only applies when `LLM_MODEL_ESCALATION` is set. |
| `LLM_API_BASE_URL` | `https://models.inference.ai.azure.com` | LLM API base URL |
| `SRE_PROMPT_PATH` | `/app/skill.md` | Path to skill.md inside the container |
| `INCIDENTS_DIR` | `/app/incidents` | Directory where incident reports are written |
| `PAGERDUTY_ROUTING_KEY` | (empty) | PagerDuty Events API v2 integration key (from Secret Manager). Required — agent creates incidents on escalation. |
| `PAGERDUTY_ESCALATION_POLICY_ID` | (empty) | PagerDuty escalation policy ID for human handoff |
| `SCALING_LIMITS` | (empty) | Comma-separated scaling bounds: `evergreen-tvevents\|1\|500\|cloud_native` |
| `MAX_CONCURRENT_ALERTS` | `3` | Maximum concurrent agent runs. Excess alerts queue with priority ordering (P1 first). |
| `ALERT_QUEUE_TTL_SECONDS` | `600` | Queued alert expiry in seconds. Stale alerts are discarded when their slot opens. |
| `MAX_TOKENS_PER_INCIDENT` | `100000` | Per-incident token ceiling. Agent escalates to human when exceeded. `0` = unlimited. |
| `MAX_TOKENS_PER_HOUR` | `0` (unlimited) | Rolling hourly token ceiling. Agent switches to escalate-only mode when exceeded. |

### Deployment

The runtime includes Terraform templates for deployment. For AWS, use ECS/Fargate resources — the container image, environment variables, and secrets pattern are the same.

### Alert Routing Setup

1. Deploy the runtime service
2. Create a PagerDuty Events API v2 integration on the target PD service
3. Set `PAGERDUTY_ROUTING_KEY` to the integration key
4. Configure your alerting platform to send webhooks to `<service_url>/webhook/alerts?auth_token=<ops-auth-token>`
5. Alerts flow to the SRE agent; PagerDuty incidents are only created when the agent escalates
