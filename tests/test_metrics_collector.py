"""Tests for Prometheus metrics collector normalization."""

from typing import Any, Dict, Union

import pytest

from app.ingestion.metrics_collector import MetricsCollector
from app.ingestion.prometheus_client import PrometheusClientError
from app.ingestion.queries import CPU_USAGE, ERROR_RATE, REQUEST_RATE, build_range_queries
from app.models.metrics import MetricsCollectionRequest, SeriesStatus


class FakePrometheusClient:
    """Simple fake client for deterministic collector tests."""

    async def query_range(
        self,
        query: str,
        start: Union[str, Any],
        end: Union[str, Any],
        step: str,
    ) -> Dict[str, Any]:
        if "container_cpu_usage_seconds_total" in query:
            return {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"namespace": "default", "pod": "api-123", "container": "api"},
                        "values": [[1710000000, "0.12"], [1710000030, "0.18"]],
                    }
                ],
            }
        if "sum(rate(http_requests_total" in query and 'status=~"5.."' not in query:
            return {"resultType": "matrix", "result": []}
        return {
            "resultType": "matrix",
            "result": [{"metric": {"namespace": "default", "pod": "api-123"}, "values": [[1710000000, "1"]]}],
        }


class ErrorPrometheusClient(FakePrometheusClient):
    """Fake client that fails for request-rate related queries."""

    async def query_range(
        self,
        query: str,
        start: Union[str, Any],
        end: Union[str, Any],
        step: str,
    ) -> Dict[str, Any]:
        if "http_requests_total" in query:
            raise PrometheusClientError("upstream timeout")
        return await super().query_range(query=query, start=start, end=end, step=step)


@pytest.mark.asyncio
async def test_collect_marks_success_and_empty_series() -> None:
    """Collector should preserve explicit empty status when no data is returned."""
    collector = MetricsCollector(prometheus_client=FakePrometheusClient())
    request = MetricsCollectionRequest(namespace="default", lookback_minutes=15, step="30s")

    snapshot = await collector.collect(request=request)

    assert snapshot.metrics[CPU_USAGE].status == SeriesStatus.SUCCESS
    assert snapshot.metrics[REQUEST_RATE].status == SeriesStatus.EMPTY
    assert snapshot.metrics[REQUEST_RATE].series[0].status == SeriesStatus.EMPTY
    assert snapshot.failed_metrics == []


@pytest.mark.asyncio
async def test_collect_marks_error_series_on_prometheus_failure() -> None:
    """Collector should mark metrics as error when query execution fails."""
    collector = MetricsCollector(prometheus_client=ErrorPrometheusClient())
    request = MetricsCollectionRequest(namespace="default", lookback_minutes=15, step="30s")

    snapshot = await collector.collect(request=request)

    assert REQUEST_RATE in snapshot.failed_metrics
    assert ERROR_RATE in snapshot.failed_metrics
    assert snapshot.metrics[REQUEST_RATE].status == SeriesStatus.ERROR
    assert snapshot.metrics[REQUEST_RATE].series[0].status == SeriesStatus.ERROR


def test_build_range_queries_supports_demo_metric_fallbacks() -> None:
    """Request/error queries should support demo Prometheus metric names."""
    request = MetricsCollectionRequest(namespace="demo", workload_name="demo-app")

    queries = build_range_queries(request)

    assert "http_requests_total" in queries[REQUEST_RATE]
    assert "demo_requests_total" in queries[REQUEST_RATE]
    assert "http_requests_total" in queries[ERROR_RATE]
    assert "demo_errors_total" in queries[ERROR_RATE]
    assert "clamp_min(" in queries[ERROR_RATE]


def test_build_range_queries_uses_cpu_memory_fallback_filters() -> None:
    """CPU and memory queries should include both strict and relaxed label filters."""
    request = MetricsCollectionRequest(namespace="demo", workload_name="demo-app")

    queries = build_range_queries(request)

    assert 'image!=""' in queries["cpu_usage"]
    assert 'container!="POD"' in queries["cpu_usage"]
    assert " or " in queries["cpu_usage"]
    assert 'image!=""' in queries["memory_usage"]
    assert 'container!="POD"' in queries["memory_usage"]
    assert " or " in queries["memory_usage"]


def test_build_range_queries_escapes_workload_name_regex() -> None:
    """Special regex chars in workload names should be escaped."""
    request = MetricsCollectionRequest(namespace="demo", workload_name="demo-app.v2")

    queries = build_range_queries(request)

    assert 'pod=~"^demo\\-app\\.v2.*"' in queries["restart_count"]

