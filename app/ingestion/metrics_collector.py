"""Metrics collector that fetches and normalizes Prometheus query results."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Dict, List

from app.ingestion.prometheus_client import PrometheusClient, PrometheusClientError
from app.ingestion.queries import build_range_queries
from app.models.metrics import (
    MetricCollectionResult,
    MetricPoint,
    MetricSeries,
    MetricsCollectionRequest,
    MetricsSnapshot,
    SeriesStatus,
)


class MetricsCollector:
    """Collect metrics for an incident context from Prometheus."""

    def __init__(self, prometheus_client: PrometheusClient) -> None:
        self.prometheus_client = prometheus_client

    async def collect(self, request: MetricsCollectionRequest) -> MetricsSnapshot:
        """Execute range queries and return normalized metrics snapshot."""
        started = perf_counter()
        query_end = datetime.now(timezone.utc)
        query_start = query_end - timedelta(minutes=request.lookback_minutes)

        metrics: Dict[str, MetricCollectionResult] = {}
        failed_metrics: List[str] = []

        for metric_name, query in build_range_queries(request).items():
            try:
                data = await self.prometheus_client.query_range(
                    query=query,
                    start=query_start,
                    end=query_end,
                    step=request.step,
                )
                normalized = self._normalize_result(metric_name, query, data)
            except PrometheusClientError as exc:
                failed_metrics.append(metric_name)
                normalized = MetricCollectionResult(
                    metric_name=metric_name,
                    query=query,
                    status=SeriesStatus.ERROR,
                    error=str(exc),
                    series=[
                        MetricSeries(
                            metric_name=metric_name,
                            query=query,
                            status=SeriesStatus.ERROR,
                            error=str(exc),
                        )
                    ],
                    sample_count=0,
                )

            metrics[metric_name] = normalized

        duration_ms = (perf_counter() - started) * 1000
        return MetricsSnapshot(
            namespace=request.namespace,
            lookback_minutes=request.lookback_minutes,
            step=request.step,
            metrics=metrics,
            failed_metrics=failed_metrics,
            duration_ms=round(duration_ms, 3),
        )

    def _normalize_result(
        self,
        metric_name: str,
        query: str,
        payload: Dict[str, Any],
    ) -> MetricCollectionResult:
        """Convert Prometheus response payload into normalized series."""
        result_type = payload.get("resultType", "")
        result = payload.get("result", [])

        if not isinstance(result, list) or len(result) == 0:
            return MetricCollectionResult(
                metric_name=metric_name,
                query=query,
                status=SeriesStatus.EMPTY,
                series=[
                    MetricSeries(
                        metric_name=metric_name,
                        query=query,
                        status=SeriesStatus.EMPTY,
                    )
                ],
                sample_count=0,
            )

        all_series: List[MetricSeries] = []
        total_samples = 0

        for entry in result:
            labels_raw = entry.get("metric", {})
            labels = labels_raw if isinstance(labels_raw, dict) else {}
            points = self._parse_points(result_type=result_type, entry=entry)
            total_samples += len(points)
            all_series.append(
                MetricSeries(
                    metric_name=metric_name,
                    query=query,
                    labels={str(k): str(v) for k, v in labels.items()},
                    points=points,
                    status=SeriesStatus.SUCCESS if points else SeriesStatus.EMPTY,
                )
            )

        status = SeriesStatus.SUCCESS if total_samples > 0 else SeriesStatus.EMPTY
        return MetricCollectionResult(
            metric_name=metric_name,
            query=query,
            status=status,
            series=all_series,
            sample_count=total_samples,
        )

    def _parse_points(self, result_type: str, entry: Dict[str, Any]) -> List[MetricPoint]:
        """Normalize matrix/vector values to a list of metric points."""
        if result_type == "matrix":
            values = entry.get("values", [])
        elif result_type == "vector":
            value = entry.get("value")
            values = [value] if value else []
        else:
            values = entry.get("values", [])

        points: List[MetricPoint] = []
        for raw_value in values:
            point = self._parse_prometheus_value(raw_value)
            if point is not None:
                points.append(point)
        return points

    def _parse_prometheus_value(self, raw_value: Any) -> MetricPoint | None:
        """Parse [timestamp, value] pair from Prometheus response."""
        if not isinstance(raw_value, (list, tuple)) or len(raw_value) < 2:
            return None
        try:
            timestamp = datetime.fromtimestamp(float(raw_value[0]), tz=timezone.utc)
            value = float(raw_value[1])
        except (TypeError, ValueError):
            return None
        return MetricPoint(timestamp=timestamp, value=value)

