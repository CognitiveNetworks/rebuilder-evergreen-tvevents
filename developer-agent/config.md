# Developer Agent Configuration

**Instructions:** Fill out this file when setting up the developer agent for a specific project. This provides project-specific context that the agent needs for daily development work.

## Project

- **Project Name:** evergreen-tvevents
- **Repository:** *[TODO: new repo URL after creation]* <!-- TODO: fill after repo creation -->
- **Primary Language:** Python 3.12
- **Framework:** FastAPI ≥ 0.115.0
- **Cloud Provider:** AWS

## Development Commands

> Commands the agent uses to build, test, lint, and run the project locally.
> Use `N/A — [reason]` for commands that don't apply (e.g., `N/A — no application database`).

| Command | Purpose |
|---|---|
| `pip install -e ".[dev]"` | Install dependencies |
| `pytest tests/ -x` | Run unit tests |
| `pytest tests/test_routes.py tests/test_ops_endpoints.py` | Run API tests |
| `pytest tests/ --cov=src/app --cov-fail-under=80` | Run integration tests |
| `pytest tests/ --cov=src/app --cov-fail-under=80` | Run all tests |
| `ruff check src/ tests/ && ruff format --check src/ tests/` | Run linter / formatter |
| `docker build -t evergreen-tvevents .` | Build container image |
| `uvicorn src.app.main:app --reload` | Run locally |
| N/A — read-only access to shared RDS blacklist table | Seed local database |

## CI/CD

- **Pipeline Tool:** GitHub Actions
- **Pipeline Definition:** `.github/workflows/ci.yml`
- **Container Registry:** *[TODO: ECR registry URL]* <!-- TODO: fill after infra provisioning -->
- **Image Tag Strategy:** Commit SHA (`<registry>/evergreen-tvevents:<sha>`)

## Environments

| Environment | URL | Terraform Workspace/Dir | Deploys |
|---|---|---|---|
| Dev | *[TODO: after infra provisioning]* <!-- TODO: fill after infra provisioning --> | `terraform/` with `envs/dev.tfvars` | Automatic on merge to `main` |
| Staging | *[TODO: after infra provisioning]* <!-- TODO: fill after infra provisioning --> | `terraform/` with `envs/staging.tfvars` | Manual promotion |
| Prod | *[TODO: after infra provisioning]* <!-- TODO: fill after infra provisioning --> | `terraform/` with `envs/prod.tfvars` | Manual promotion |

### Terraform

- **State Backend:** `s3://evergreen-tvevents-terraform-state`
- **Terraform Directory:** `terraform/`
- **Variable Files:** `envs/dev.tfvars`, `envs/staging.tfvars`, `envs/prod.tfvars`

## Services

> List all services in this project. Each service should have its own section in a multi-service project.

| Service | Directory | Port | Description |
|---|---|---|---|
| evergreen-tvevents | `src/app/` | 8000 | TV telemetry event ingestion and delivery service |

## Dependencies

### Internal

| Dependency | Type | Registry | Version |
|---|---|---|---|
| cnlib | Vendored library | Container image | Bundled |

### External

| Dependency | Purpose | Docs |
|---|---|---|
| PostgreSQL RDS | Blacklist channel ID lookup (read-only) | *[TODO: internal docs link]* <!-- TODO: fill after infra provisioning --> |
| Apache Kafka (MSK) | Event delivery (replaces Firehose) | *[TODO: internal docs link]* <!-- TODO: fill after infra provisioning --> |
| cnlib | Security hash validation (token_hash) and structured logging (log) | Vendored in container image |
| New Relic | APM and observability via OTEL export | *[TODO: New Relic docs link]* <!-- TODO: fill after infra provisioning --> |

## Secrets

> Reference only — never store actual secret values here.

| Secret | Secrets Manager Key | Used By |
|---|---|---|
| T1_SALT | `tvevents/t1-salt` | Request validation (HMAC hash) |
| Kafka credentials | `tvevents/kafka-credentials` | Kafka module auth |
| RDS credentials | `tvevents/rds-credentials` | RDS module connection |
| OPS_AUTH_TOKEN | `tvevents/ops-auth-token` | /ops/* endpoint auth |

## Monitoring

- **Dashboard URL:** *[TODO: after setup]* <!-- TODO: fill after infra provisioning -->
- **Alerting:** *[TODO: PagerDuty service ID after setup]* <!-- TODO: fill after infra provisioning -->
- **Log Query:** *[TODO: saved query URL after setup]* <!-- TODO: fill after infra provisioning -->

## Telemetry (OpenTelemetry)

- **OTEL Collector Endpoint:** *[TODO: OTLP endpoint]* <!-- TODO: fill after infra provisioning -->
- **Service Name Convention:** evergreen-tvevents
- **Resource Attributes:** `deployment.environment=${ENVIRONMENT},service.version=${COMMIT_SHA}`
- **APM Platform:** New Relic (via OTEL export headers)
- **Trace Sampling:** `1.0` for dev/staging, `0.1` for prod

## SRE Agent Integration

- **SRE Agent Config:** `../sre-agent/config.md`
- **Service Registry Entry:** `evergreen-tvevents|*[TODO: URL]*|true` <!-- TODO: fill after infra provisioning -->
