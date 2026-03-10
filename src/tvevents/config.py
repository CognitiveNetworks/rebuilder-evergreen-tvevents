"""Application configuration via pydantic-settings."""


import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-based configuration for tvevents-k8s."""

    # Application
    env: str = os.getenv("ENV", "development")
    log_level: str = "INFO"
    service_name: str = "tvevents-k8s"
    zoo: str = os.getenv("FLASK_ENV", os.getenv("ENV", "development"))

    # Security
    t1_salt: str = ""

    # RDS
    rds_host: str = "localhost"
    rds_db: str = "tvevents"
    rds_user: str = "postgres"
    rds_pass: str = ""
    rds_port: int = 5432

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_mechanism: str = "SCRAM-SHA-512"

    # Kafka Topics
    kafka_topic_evergreen: str = ""
    kafka_topic_legacy: str = ""
    kafka_topic_debug_evergreen: str = ""
    kafka_topic_debug_legacy: str = ""

    # Feature flags
    send_evergreen: bool = False
    send_legacy: bool = False
    tvevents_debug: bool = False

    # AWS
    aws_region: str = "us-east-1"

    # OTEL
    otel_service_name: str = "tvevents-k8s"
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""

    # Cache
    blacklist_cache_filepath: str = "/tmp/.blacklisted_channel_ids_cache"

    model_config = {"env_prefix": "", "case_sensitive": False}

    @property
    def valid_kafka_topics(self) -> list[str]:
        """Return list of active Kafka topics based on feature flags."""
        topics: list[str] = []
        if self.send_evergreen and self.kafka_topic_evergreen:
            topics.append(self.kafka_topic_evergreen)
        if self.send_legacy and self.kafka_topic_legacy:
            topics.append(self.kafka_topic_legacy)
        return topics

    @property
    def valid_debug_kafka_topics(self) -> list[str]:
        """Return list of active debug Kafka topics based on feature flags."""
        topics: list[str] = []
        if self.send_evergreen and self.kafka_topic_debug_evergreen:
            topics.append(self.kafka_topic_debug_evergreen)
        if self.send_legacy and self.kafka_topic_debug_legacy:
            topics.append(self.kafka_topic_debug_legacy)
        return topics


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the singleton Settings instance."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings
