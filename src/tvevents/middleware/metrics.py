"""Request metrics middleware — Golden Signals / RED metrics collection.

Intercepts every request to record latency, traffic, and error counts in
an in-memory :class:`MetricsCollector` singleton.  The ``/ops/metrics``
endpoint reads from this collector to return real, live data.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from tvevents.api.models import GoldenSignals, LatencyMetrics, MetricsResponse, RedMetrics

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


class MetricsCollector:
    """Thread-safe in-memory metrics store.

    Collects per-request timing data and error counts so that the ops
    metrics endpoint can compute percentiles and rates from real traffic.
    """

    _instance: MetricsCollector | None = None
    _lock = threading.Lock()

    def __new__(cls) -> MetricsCollector:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self) -> None:
        self._request_count: int = 0
        self._error_count: int = 0
        self._durations: list[float] = []
        self._start_time: float = time.monotonic()

        # Per-endpoint breakdown: key = "METHOD path"
        self._endpoint_counts: dict[str, int] = defaultdict(int)
        self._endpoint_errors: dict[str, int] = defaultdict(int)
        self._endpoint_durations: dict[str, list[float]] = defaultdict(list)

        # Per (method, path, status) for fine-grained counters
        self._status_counts: dict[tuple[str, str, int], int] = defaultdict(int)

        # Error type breakdown
        self._error_type_counts: dict[tuple[str, str, str], int] = defaultdict(int)

        self._data_lock = threading.Lock()

        # Saturation data (populated externally by services)
        self._saturation: dict[str, float] = {}

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        error_type: str | None = None,
    ) -> None:
        """Record a single completed request."""
        key = f"{method} {path}"
        with self._data_lock:
            self._request_count += 1
            self._durations.append(duration_ms)
            self._endpoint_counts[key] += 1
            self._endpoint_durations[key].append(duration_ms)
            self._status_counts[(method, path, status_code)] += 1

            if status_code >= 400:
                self._error_count += 1
                self._endpoint_errors[key] += 1
                if error_type:
                    self._error_type_counts[(method, path, error_type)] += 1

    def update_saturation(self, name: str, utilisation: float) -> None:
        """Update a named saturation metric (0.0 – 1.0)."""
        with self._data_lock:
            self._saturation[name] = utilisation

    def get_metrics(self) -> MetricsResponse:
        """Compute current Golden Signals + RED from collected data."""
        with self._data_lock:
            elapsed_s = max(time.monotonic() - self._start_time, 0.001)
            total = self._request_count
            errors = self._error_count
            durations = list(self._durations)

            latency = self._compute_percentiles(durations)

            golden = GoldenSignals(
                latency=latency,
                traffic_total=total,
                traffic_per_sec=round(total / elapsed_s, 2),
                error_count=errors,
                error_rate=round(errors / max(total, 1), 6),
                saturation=dict(self._saturation),
            )

            red = RedMetrics(
                rate=round(total / elapsed_s, 2),
                errors=round(errors / max(total, 1), 6),
                duration_p50=latency.p50,
                duration_p95=latency.p95,
                duration_p99=latency.p99,
            )

            by_endpoint: dict[str, RedMetrics] = {}
            for key, ep_durations in self._endpoint_durations.items():
                ep_total = self._endpoint_counts[key]
                ep_errors = self._endpoint_errors.get(key, 0)
                ep_latency = self._compute_percentiles(ep_durations)
                by_endpoint[key] = RedMetrics(
                    rate=round(ep_total / elapsed_s, 2),
                    errors=round(ep_errors / max(ep_total, 1), 6),
                    duration_p50=ep_latency.p50,
                    duration_p95=ep_latency.p95,
                    duration_p99=ep_latency.p99,
                )

        return MetricsResponse(
            golden_signals=golden,
            red=red,
            by_endpoint=by_endpoint,
        )

    @staticmethod
    def _compute_percentiles(durations: list[float]) -> LatencyMetrics:
        """Compute p50, p95, p99 from a list of durations (ms)."""
        if not durations:
            return LatencyMetrics(p50=0.0, p95=0.0, p99=0.0)
        sorted_d = sorted(durations)
        n = len(sorted_d)
        return LatencyMetrics(
            p50=round(sorted_d[min(math.ceil(n * 0.50) - 1, n - 1)], 3),
            p95=round(sorted_d[min(math.ceil(n * 0.95) - 1, n - 1)], 3),
            p99=round(sorted_d[min(math.ceil(n * 0.99) - 1, n - 1)], 3),
        )


class MetricsMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that records request timing and status."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        response: Response | None = None
        error_type: str | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            status = response.status_code if response else 500
            path = request.url.path
            method = request.method
            MetricsCollector().record_request(
                method=method,
                path=path,
                status_code=status,
                duration_ms=elapsed_ms,
                error_type=error_type,
            )

        return response
