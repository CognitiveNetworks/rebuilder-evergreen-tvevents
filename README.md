# tvevents-k8s

TV event ingestion service — validates, transforms, and delivers smart TV telemetry to Apache Kafka.

## Overview

`tvevents-k8s` receives TV event payloads via HTTP POST, validates them (HMAC security hash, required fields, event-type-specific schemas), transforms and flattens the JSON, optionally obfuscates blacklisted channels, and delivers the output to one or more Kafka topics.

## Architecture

- **Framework**: FastAPI + Uvicorn
- **Event Delivery**: Apache Kafka (AWS MSK) via `confluent-kafka`
- **Database**: PostgreSQL (AWS RDS) via `psycopg2` — blacklisted channel lookup
- **Cache**: File-based blacklist cache at `/tmp/.blacklisted_channel_ids_cache`
- **Observability**: OTEL auto-instrumentation → New Relic OTLP endpoint
- **Deployment**: Docker → Kubernetes (Helm)

## Project Structure

```
src/tvevents/
├── __init__.py
├── config.py              # pydantic-settings configuration
├── deps.py                # singleton dependency holders
├── main.py                # FastAPI app entry point
├── api/
│   ├── models.py          # Pydantic request/response models
│   ├── ops.py             # /ops/* diagnostic & remediation endpoints
│   └── routes.py          # POST /, GET /status, GET /health
├── domain/
│   ├── delivery.py        # Kafka topic delivery
│   ├── event_types.py     # event type dispatch and validation
│   ├── obfuscation.py     # channel blacklist obfuscation
│   ├── security.py        # HMAC security hash validation
│   ├── transform.py       # JSON flattening and output generation
│   └── validation.py      # request validation and exceptions
├── infrastructure/
│   ├── cache.py           # file-based blacklist cache
│   └── database.py        # RDS client wrapper
└── middleware/
    └── metrics.py         # request metrics (Golden Signals / RED)
```

## Development

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (for local dependencies)

### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your local values
```

### Run Locally

```bash
# Start dependencies (PostgreSQL, Kafka)
docker-compose up -d postgres kafka

# Run the service
PYTHONPATH=src uvicorn tvevents.main:app --reload --port 8000
```

### Run Tests

```bash
PYTHONPATH=src pytest tests/ -v --tb=short
```

### Lock Dependencies

```bash
bash scripts/lock.sh
```

## API Endpoints

| Method | Path              | Description                              |
|--------|-------------------|------------------------------------------|
| POST   | `/`               | TV event ingestion                       |
| GET    | `/status`         | Health check (legacy compat)             |
| GET    | `/health`         | Health check alias                       |
| GET    | `/ops/status`     | Composite health verdict                 |
| GET    | `/ops/health`     | Dependency health check                  |
| GET    | `/ops/metrics`    | Golden Signals + RED metrics             |
| GET    | `/ops/config`     | Runtime configuration (secrets redacted) |
| GET    | `/ops/dependencies` | Dependency connectivity                |
| GET    | `/ops/errors`     | Recent error summary                     |
| GET    | `/ops/circuits`   | Circuit breaker state                    |
| POST   | `/ops/drain`      | Toggle drain mode                        |
| POST   | `/ops/cache/flush` | Flush and reload blacklist cache        |
| POST   | `/ops/loglevel`   | Change runtime log level                 |
| POST   | `/ops/scale`      | Scale (delegated to Kubernetes HPA)      |

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Description |
|----------|-------------|
| `T1_SALT` | HMAC salt for security hash validation |
| `RDS_HOST`, `RDS_DB`, `RDS_USER`, `RDS_PASS`, `RDS_PORT` | PostgreSQL connection |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses |
| `KAFKA_TOPIC_EVERGREEN`, `KAFKA_TOPIC_LEGACY` | Kafka topic names |
| `SEND_EVERGREEN`, `SEND_LEGACY` | Feature flags for topic delivery |
| `TVEVENTS_DEBUG` | Enable debug topic delivery |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTEL collector endpoint |

## ADRs

See [`docs/adr/`](docs/adr/) for architectural decision records.

## CI/CD

CI runs on every push via GitHub Actions (`.github/workflows/ci.yml`):
1. Lint (ruff)
2. Type check (mypy)
3. Unit tests (pytest)
4. Coverage check (≥80%)
5. Docker build verification
