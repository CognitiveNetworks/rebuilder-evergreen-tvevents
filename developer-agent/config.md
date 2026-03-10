# Developer Agent Configuration

**Instructions:** Fill out this file when setting up the developer agent for a specific project. This provides project-specific context that the agent needs for daily development work.

## Project

- **Project Name:** tvevents-k8s
- **Repository:** CognitiveNetworks/rebuilder-evergreen-tvevents
- **Primary Language:** Python 3.12
- **Framework:** FastAPI (latest stable)
- **Cloud Provider:** AWS

## Development Commands

> Commands the agent uses to build, test, lint, and run the project locally.
> Use `N/A — [reason]` for commands that don't apply (e.g., `N/A — no application database`).

| Command | Purpose |
|---|---|
| `pip install -r requirements.txt && pip install -e '.[dev]'` | Install dependencies |
| `pytest tests/ -v --tb=short` | Run unit tests |
| `pytest tests/ -v -k "test_route"` | Run API tests |
| `bash scripts/e2e-smoke.sh` | Run integration tests |
| `pytest -v --tb=short --cov=src/tvevents` | Run all tests |
| `ruff check . && ruff format --check . && mypy src/` | Run linter / formatter / type check |
| `docker build -t tvevents-k8s .` | Build container image |
| `uvicorn src.tvevents.main:app --reload --port 8000` | Run locally |
| `psql -f scripts/seed_db.sql` | Seed blacklisted channel IDs |

## CI/CD

- **Pipeline Tool:** GitHub Actions
- **Pipeline Definition:** `.github/workflows/ci.yml`
- **Container Registry:** AWS ECR (`[TODO: account-id].dkr.ecr.us-east-1.amazonaws.com/tvevents-k8s`)
- **Image Tag Strategy:** Commit SHA (`<registry>/<service>:<sha>`)

## Environments

| Environment | URL | Terraform Workspace/Dir | Deploys |
|---|---|---|---|
| Dev | *[TODO: after infra provisioning]* | `terraform/` with `envs/dev.tfvars` | Automatic on merge to `main` |
| Staging | *[TODO: after infra provisioning]* | `terraform/` with `envs/staging.tfvars` | Manual promotion |
| Prod | *[TODO: after infra provisioning]* | `terraform/` with `envs/prod.tfvars` | Manual promotion |

### Terraform

- **State Backend:** `s3://tvevents-k8s-terraform-state`
- **Terraform Directory:** `terraform/`
- **Variable Files:** `envs/dev.tfvars`, `envs/staging.tfvars`, `envs/prod.tfvars`

## Services

> List all services in this project. Each service should have its own section in a multi-service project.

| Service | Directory | Port | Description |
|---|---|---|---|
| tvevents-k8s | src/tvevents/ | 8000 | TV event ingestion service |

## Dependencies

### Internal

| Dependency | Type | Registry | Version |
|---|---|---|---|
| rebuilder-rds-module | Python package | Local (output/) | 0.1.0 |
| rebuilder-kafka-module | Python package | Local (output/) | 0.1.0 |

### External

| Dependency | Purpose | Docs |
|---|---|---|
| AWS RDS PostgreSQL | Blacklisted channel ID lookups | [AWS RDS docs](https://docs.aws.amazon.com/rds/) |
| AWS MSK (Kafka) | Event delivery (replacing Firehose) | [AWS MSK docs](https://docs.aws.amazon.com/msk/) |
| New Relic | APM / OTEL telemetry target | [NR OTLP docs](https://docs.newrelic.com/docs/opentelemetry/) |

## Secrets

> Reference only — never store actual secret values here.

| Secret | Secrets Manager Key | Used By |
|---|---|---|
| T1_SALT | [TODO: secrets manager path] | tvevents-k8s |
| RDS_PASS | [TODO: secrets manager path] | tvevents-k8s |
| ACR_DATA_MSK_USERNAME | [TODO: secrets manager path] | tvevents-k8s |
| ACR_DATA_MSK_PASSWORD | [TODO: secrets manager path] | tvevents-k8s |
| OTEL_EXPORTER_OTLP_HEADERS | [TODO: secrets manager path] | tvevents-k8s |

## Monitoring

- **Dashboard URL:** *[TODO: after setup]*
- **Alerting:** *[TODO: PagerDuty service ID after setup]*
- **Log Query:** *[TODO: saved query URL after setup]*

## Telemetry (OpenTelemetry)

- **OTEL Collector Endpoint:** `https://otlp.nr-data.net:443`
- **Service Name Convention:** tvevents-k8s
- **Resource Attributes:** `deployment.environment=${ENVIRONMENT},service.version=${COMMIT_SHA}`
- **APM Platform:** New Relic (via OTLP HTTP exporters)
- **Trace Sampling:** `1.0` for dev/staging, `0.1` for prod

## SRE Agent Integration

- **SRE Agent Config:** `../sre-agent/config.md`
- **Service Registry Entry:** `tvevents-k8s|[TODO: URL after infra provisioning]|true`
