# evergreen-tvevents

High-throughput TV telemetry ingestion microservice for Vizio SmartCast devices.

## Overview

Receives event data from SmartCast TVs via HTTP POST, validates security hashes,
classifies events into three types (NativeAppTelemetry, AcrTunerData, PlatformTelemetry),
applies channel obfuscation, and delivers processed payloads to Apache Kafka topics.

## Quick Start

```bash
# Copy environment file
cp .env.example .env

# Start local services (PostgreSQL + OTEL Collector)
docker compose up -d

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ --cov=app --cov-fail-under=80

# Run locally
uvicorn app.main:app --reload
```

## Development

### Lock Dependencies

```bash
bash scripts/lock.sh
```

### Lint & Type Check

```bash
ruff check src/ tests/
mypy src/app/
```

### Test Coverage

```bash
pytest tests/ --cov=app --cov-fail-under=80
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Ingest TV event data |
| GET | `/status` | Basic health check |
| GET | `/health` | Dependency-aware health check (503 when unhealthy/draining) |
| GET | `/ops/health` | Deep health check (Kafka, RDS, cache) |
| GET | `/ops/status` | Composite status rollup (healthy/degraded/unhealthy) |
| GET | `/ops/metrics` | Golden Signals and RED metrics |
| GET | `/ops/config` | Runtime configuration (no secrets) |
| GET | `/ops/dependencies` | Dependency connectivity status |
| GET | `/ops/cache` | Blacklist cache statistics |
| GET | `/ops/errors` | Recent error summary |
| GET | `/ops/scale` | Scaling information (KEDA) |
| POST | `/ops/cache/refresh` | Refresh blacklist cache from RDS |
| POST | `/ops/cache/flush` | Flush and refresh blacklist cache |
| POST | `/ops/drain` | Enable/disable drain mode |
| POST | `/ops/circuits` | Circuit breaker status |
| POST | `/ops/log-level` | Change log level at runtime |
| POST | `/ops/loglevel` | Change log level (canonical path) |

## Architecture

```
POST / → validation → event_type classification → output generation → Kafka delivery
                                                        ↓
                                              obfuscation (if blacklisted)
```

### External Dependencies

- **Apache Kafka** — event delivery (via standalone kafka_module)
- **PostgreSQL RDS** — blacklist data (via standalone rds_module)
- **cnlib** — T1_SALT security hash validation + structured logging

## Environment Variables

See [.env.example](.env.example) for the complete list with descriptions.
