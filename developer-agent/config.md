# Developer Agent Configuration

**Instructions:** Fill out this file when setting up the developer agent for a specific project. This provides project-specific context that the agent needs for daily development work.

## Project

- **Project Name:** rebuilder-evergreen-tvevents
- **Repository:** rebuilder-evergreen-tvevents
- **Primary Language:** Python 3.12
- **Framework:** FastAPI ≥0.115
- **Cloud Provider:** AWS

## Development Commands

> Commands the agent uses to build, test, lint, and run the project locally.
> Use `N/A — [reason]` for commands that don't apply (e.g., `N/A — no application database`).

| Command | Purpose |
|---|---|
| `pip install -e ".[dev]"` | Install dependencies |
| `pytest -v` | Run unit tests |
| `pytest tests/test_routes.py -v` | Run API tests |
| `pytest --cov=src/tvevents` | Run all tests with coverage |
| `ruff check .` | Run linter |
| `ruff format --check .` | Check formatting |
| `mypy src/ --strict` | Run type checker |
| `docker build --platform linux/amd64 -t rebuilder-evergreen-tvevents:dev .` | Build container image |
| `docker compose up` | Run locally |
| `uvicorn tvevents.main:app --reload --port 8000` | Run dev server |

## CI/CD

- **Pipeline Tool:** GitHub Actions
- **Pipeline Definition:** `.github/workflows/ci.yml`
- **Container Registry:** AWS ECR
- **Image Tag Strategy:** Commit SHA (`<registry>/rebuilder-evergreen-tvevents:<sha>`)

## Environments

| Environment | URL | Terraform Workspace/Dir | Deploys |
|---|---|---|---|
| Dev | *[TODO: after infra provisioning]* <!-- TODO --> | `terraform/` with `envs/dev.tfvars` | Automatic on merge to `main` |
| Staging | *[TODO: after infra provisioning]* <!-- TODO --> | `terraform/` with `envs/staging.tfvars` | Manual promotion |
| Prod | *[TODO: after infra provisioning]* <!-- TODO --> | `terraform/` with `envs/prod.tfvars` | Manual promotion |

### Terraform

- **State Backend:** `s3://rebuilder-evergreen-tvevents-terraform-state`
- **Terraform Directory:** `terraform/`
- **Variable Files:** `envs/dev.tfvars`, `envs/staging.tfvars`, `envs/prod.tfvars`

## Services

> List all services in this project. Each service should have its own section in a multi-service project.

| Service | Directory | Port | Description |
|---|---|---|---|
| tvevents-api | `src/tvevents/` | 8000 | FastAPI TV event ingestion service |

## Dependencies

### Internal

| Dependency | Type | Registry | Version |
|---|---|---|---|
| rebuilder-redis-module | Python library | Private PyPI | *[TODO: version]* <!-- TODO --> |

### External

| Dependency | Purpose | Docs |
|---|---|---|
| PostgreSQL (AWS RDS) | Blacklist storage and persistent state via asyncpg | [RDS docs](https://docs.aws.amazon.com/rds/) |
| Redis (AWS ElastiCache) | Low-latency caching via rebuilder-redis-module | [ElastiCache docs](https://docs.aws.amazon.com/elasticache/) |
| Apache Kafka (AWS MSK) | Event delivery backbone via confluent-kafka | [MSK docs](https://docs.aws.amazon.com/msk/) |
| OpenTelemetry Collector | Telemetry data export (traces, metrics, logs) | [OTEL Collector docs](https://opentelemetry.io/docs/collector/) |

## Secrets

> Reference only — never store actual secret values here.

| Secret | Secrets Manager Key | Used By |
|---|---|---|
| RDS database credentials | *[TODO: AWS Secrets Manager ARN]* <!-- TODO --> | tvevents-api |
| Redis auth token | *[TODO: AWS Secrets Manager ARN]* <!-- TODO --> | tvevents-api |
| Kafka SASL credentials | *[TODO: AWS Secrets Manager ARN]* <!-- TODO --> | tvevents-api |
| T1_SALT (HMAC salt) | *[TODO: AWS Secrets Manager ARN]* <!-- TODO --> | tvevents-api |

## Monitoring

- **Dashboard URL:** *[TODO: after setup]* <!-- TODO -->
- **Alerting:** *[TODO: PagerDuty service ID after setup]* <!-- TODO -->
- **Log Query:** *[TODO: saved query URL after setup]* <!-- TODO -->

## Telemetry (OpenTelemetry)

- **OTEL Collector Endpoint:** *[TODO: OTLP endpoint]* <!-- TODO -->
- **Service Name Convention:** `rebuilder-evergreen-tvevents`
- **Resource Attributes:** `deployment.environment=${ENVIRONMENT},service.version=${COMMIT_SHA}`
- **APM Platform:** OpenTelemetry Collector (OTLP export)
- **Trace Sampling:** `1.0` for dev/staging, `0.1` for prod

## SRE Agent Integration

- **SRE Agent Config:** `../sre-agent/config.md`
- **Service Registry Entry:** `rebuilder-evergreen-tvevents|*[TODO: URL]*|critical` <!-- TODO -->
