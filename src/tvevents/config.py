"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables (or a .env file for
local development).  Secrets such as ``t1_salt`` have **no default** — the
service cannot start without them.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the tvevents ingestion service."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env")

    # ── Service ──────────────────────────────────────────────────────────
    service_name: str = "rebuilder-evergreen-tvevents"
    zoo: str = "development"  # Environment name (replaces FLASK_ENV)
    debug: bool = False
    log_level: str = "INFO"

    # ── HMAC ─────────────────────────────────────────────────────────────
    t1_salt: str  # Required — no default (from AWS Secrets Manager)

    # ── Database (RDS) ───────────────────────────────────────────────────
    rds_host: str = "localhost"
    rds_db: str = "tvevents"
    rds_user: str = "tvevents"
    rds_pass: str = ""
    rds_port: int = 5432

    # ── Redis ────────────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_ssl: bool = False
    redis_db: int = 0

    # ── Kafka ────────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "tvevents"
    kafka_debug_topic: str = "tvevents-debug"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None
    kafka_delivery_enabled: bool = True

    # ── Feature flags ────────────────────────────────────────────────────
    tvevents_debug: bool = False
    send_evergreen: bool = True
    legacy_firehose_bridge_enabled: bool = False

    # ── Cache ────────────────────────────────────────────────────────────
    blacklist_cache_ttl: int = 300  # seconds

    # ── OTEL ─────────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_traces_sampler_arg: float = 1.0
