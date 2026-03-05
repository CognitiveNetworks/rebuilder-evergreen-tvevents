# rebuilder-evergreen-tvevents

FastAPI TV event ingestion service — rebuilt from the legacy `evergreen-tvevents` Node.js application. Receives TV viewing events via HMAC-authenticated HTTP, validates and transforms payloads, checks a Redis-cached blacklist, and delivers events to Kafka for downstream consumers.

## Architecture

```
Client → POST /v1/events (HMAC auth)
  → Payload validation & schema check
  → Blacklist lookup (Redis cache ← RDS refresh)
  → Kafka delivery (tvevents topic)
  → Optional debug topic (tvevents-debug)
```

**Dependencies:**
- **Kafka (MSK)** — event delivery to downstream consumers
- **PostgreSQL (RDS)** — blacklisted station/channel lookup
- **Redis (ElastiCache)** — blacklist cache layer with TTL-based refresh
- **OpenTelemetry Collector** — traces, metrics, and logs export

For the full target architecture, see [docs/component-overview.md](docs/component-overview.md).

## Quick Start

```bash
# Clone and enter the project
cd rebuilder-evergreen-tvevents

# Copy environment config
cp .env.example .env

# Start all services (API, Redis, Postgres, Kafka, OTEL collector)
docker compose up -d

# Verify
curl http://localhost:8000/health
```

## Development

### Prerequisites

- Python 3.12+
- Docker & Docker Compose

### Local Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the internal Redis module dependency first
pip install -e output/rebuilder-redis-module

# Install the project with dev dependencies
pip install -e ".[dev]"

# Start infrastructure services
docker compose up -d redis postgres kafka otel-collector

# Copy environment file
cp .env.example .env

# Run the API locally
uvicorn tvevents.main:app --reload --port 8000
```

### Commands

| Command | Purpose |
|---|---|
| `pip install -e ".[dev]"` | Install all dependencies |
| `pytest` | Run unit tests |
| `pytest --cov=tvevents --cov-report=term-missing` | Run tests with coverage |
| `ruff check .` | Lint |
| `ruff format .` | Format code |
| `ruff format --check .` | Check formatting |
| `mypy src/ --strict` | Type check |
| `docker compose up -d` | Start local stack |
| `uvicorn tvevents.main:app --reload` | Run API locally |

## API Endpoints

### Core

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Dependency health check (Kafka, RDS, Redis) — returns 200/503 |
| `POST` | `/v1/events` | Ingest a TV event (HMAC-authenticated) |

### Ops — Diagnostics (`/ops`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/ops/status` | Service status with uptime and environment |
| `GET` | `/ops/health` | Detailed per-dependency health (Kafka, RDS, Redis, OTEL) |
| `GET` | `/ops/metrics` | Golden Signals and RED metrics from live traffic |
| `GET` | `/ops/config` | Sanitised runtime configuration (secrets redacted) |
| `GET` | `/ops/dependencies` | List all dependencies with status and latency |
| `GET` | `/ops/errors` | Recent errors (last 100 from circular buffer) |

### Ops — Remediation (`/ops`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/ops/drain` | Enable or disable drain mode |
| `POST` | `/ops/cache/flush` | Flush the Redis blacklist cache |
| `POST` | `/ops/circuits` | Open or close circuit breakers |
| `PUT` | `/ops/loglevel` | Change log level at runtime |
| `POST` | `/ops/scale` | Advisory scaling recommendation based on current throughput |

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for the complete list.

Key variables:

| Variable | Description | Default |
|---|---|---|
| `T1_SALT` | HMAC authentication salt | *(required)* |
| `RDS_HOST` | PostgreSQL host | `localhost` |
| `REDIS_HOST` | Redis host | `localhost` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `localhost:9092` |
| `KAFKA_TOPIC` | Primary Kafka topic | `tvevents` |
| `KAFKA_DELIVERY_ENABLED` | Enable/disable Kafka delivery | `true` |
| `BLACKLIST_CACHE_TTL` | Blacklist cache TTL in seconds | `300` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://localhost:4317` |

## Deployment

### Docker Build

```bash
docker build --platform linux/amd64 -t rebuilder-evergreen-tvevents:latest .
```

### CI/CD

The GitHub Actions pipeline (`.github/workflows/ci.yml`) runs on every push to `main` and on pull requests:

1. **Lint** — `ruff check` and `ruff format --check`
2. **Type check** — `mypy src/ --strict`
3. **Test** — `pytest` with coverage (80% minimum)
4. **Scan** — Trivy vulnerability scan on the Docker image
5. **Deploy** — Build, push to ECR, deploy to dev (main branch only)
6. **Terraform plan** — Posted as PR comment on pull requests

### Terraform

Infrastructure is defined in `terraform/` with per-environment variable files:

```bash
cd terraform
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars
```

Managed resources: MSK topics, ElastiCache Redis, IAM roles, EKS namespace.

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=tvevents --cov-report=term-missing -v

# Quality gates
ruff check .                  # Lint
ruff format --check .         # Format
mypy src/ --strict            # Type check
```

Coverage threshold: **80%** (enforced in `pyproject.toml`).

## Project Structure

```
├── src/tvevents/          # Application code
│   ├── api/               # FastAPI routes, models, health check
│   ├── domain/            # Business logic, validation, schemas
│   ├── middleware/         # Metrics middleware
│   ├── ops/               # Diagnostics and remediation endpoints
│   ├── services/          # Kafka, RDS, Redis, cache clients
│   ├── config.py          # Pydantic settings
│   └── main.py            # App factory, OTEL bootstrap, lifespan
├── tests/                 # Test suite
├── terraform/             # Infrastructure as code
├── scripts/               # Database seed scripts
├── output/                # Build outputs (rebuilder-redis-module)
├── developer-agent/       # AI agent configuration
├── sre-agent/             # SRE agent configuration
└── docs/                  # Architecture, ADRs, feature parity
```

## Related Documents

- [Product Requirements (PRD)](output/prd.md)
- [Component Overview](docs/component-overview.md)
- [Feature Parity](docs/feature-parity.md)
- [Data Migration Mapping](docs/data-migration-mapping.md)
- [Architecture Decision Records](docs/adr/)
- [Developer Agent Standards](developer-agent/skill.md)
- [Developer Agent Config](developer-agent/config.md)
