"""Request metrics middleware — Golden Signals and RED method."""


import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class MetricsState:
    """In-memory metrics state for /ops/metrics."""

    def __init__(self) -> None:
        self.request_count: int = 0
        self.error_count: int = 0
        self.in_flight: int = 0
        self.status_counts: dict[int, int] = defaultdict(int)
        self.durations: list[float] = []
        self._max_durations: int = 10000

    def record(self, status_code: int, duration: float) -> None:
        """Record a completed request."""
        self.request_count += 1
        self.status_counts[status_code] += 1
        if status_code >= 400:
            self.error_count += 1
        self.durations.append(duration)
        if len(self.durations) > self._max_durations:
            self.durations = self.durations[-self._max_durations:]

    def percentile(self, p: float) -> float:
        """Calculate a percentile from recorded durations."""
        if not self.durations:
            return 0.0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * p / 100.0)
        idx = min(idx, len(sorted_d) - 1)
        return sorted_d[idx]

    def summary(self) -> dict[str, Any]:
        """Return metrics summary for /ops/metrics."""
        rate = self.request_count
        error_ratio = (self.error_count / self.request_count) if self.request_count > 0 else 0.0
        return {
            "golden_signals": {
                "latency_p50_ms": round(self.percentile(50) * 1000, 2),
                "latency_p95_ms": round(self.percentile(95) * 1000, 2),
                "latency_p99_ms": round(self.percentile(99) * 1000, 2),
                "traffic_total_requests": rate,
                "errors_total": self.error_count,
                "errors_by_status": dict(self.status_counts),
                "saturation_in_flight": self.in_flight,
            },
            "red": {
                "rate_total": rate,
                "errors_ratio": round(error_ratio, 6),
                "duration_p50_ms": round(self.percentile(50) * 1000, 2),
                "duration_p95_ms": round(self.percentile(95) * 1000, 2),
                "duration_p99_ms": round(self.percentile(99) * 1000, 2),
            },
        }


metrics_state = MetricsState()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records request metrics for Golden Signals and RED."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        metrics_state.in_flight += 1
        start = time.monotonic()
        try:
            response = await call_next(request)
            duration = time.monotonic() - start
            metrics_state.record(response.status_code, duration)
            return response
        except Exception:
            duration = time.monotonic() - start
            metrics_state.record(500, duration)
            raise
        finally:
            metrics_state.in_flight -= 1
