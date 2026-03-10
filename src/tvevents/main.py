"""FastAPI application entry point for tvevents-k8s."""


import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


from fastapi import FastAPI

from tvevents import __version__
from tvevents.api.ops import is_draining
from tvevents.api.routes import router as core_router
from tvevents.api.ops import router as ops_router
from tvevents.config import get_settings
from tvevents.infrastructure.cache import BlacklistCache
from tvevents.infrastructure.database import RdsClient
from tvevents.middleware.metrics import MetricsMiddleware

logger = logging.getLogger(__name__)

_rds_client: RdsClient | None = None
_blacklist_cache: BlacklistCache | None = None


def get_rds_client() -> RdsClient:
    """Get the singleton RDS client."""
    global _rds_client  # noqa: PLW0603
    if _rds_client is None:
        _rds_client = RdsClient()
    return _rds_client


def get_blacklist_cache() -> BlacklistCache:
    """Get the singleton blacklist cache."""
    global _blacklist_cache  # noqa: PLW0603
    if _blacklist_cache is None:
        _blacklist_cache = BlacklistCache()
    return _blacklist_cache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown hooks."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    logger.info(
        "Starting tvevents-k8s v%s env=%s",
        __version__,
        settings.env,
    )

    # Initialize blacklist cache from file (written by entrypoint.sh)
    cache = get_blacklist_cache()
    cached = cache.read()
    if cached is not None:
        logger.info("Loaded %d blacklisted channel IDs from file cache", len(cached))
    else:
        logger.warning(
            "Blacklist cache file not found — will load from RDS on first request"
        )

    yield

    # Shutdown
    logger.info("Shutting down tvevents-k8s")
    try:
        from tvevents.domain.delivery import close_producer
        close_producer()
    except Exception as e:
        logger.error("Error closing Kafka producer: %s", e)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="tvevents-k8s",
        version=__version__,
        description="TV event ingestion service — validates, transforms, and delivers smart TV telemetry to Kafka",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(MetricsMiddleware)

    # Routers
    app.include_router(core_router)
    app.include_router(ops_router)

    logger.info(
        "App configured: send_evergreen=%s send_legacy=%s debug=%s",
        settings.send_evergreen,
        settings.send_legacy,
        settings.tvevents_debug,
    )

    return app


app = create_app()
