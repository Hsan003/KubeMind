"""API tests for metrics collection routes."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.api.routes as routes_module
from app.main import app
from app.models.metrics import MetricCollectionResult, MetricsSnapshot, SeriesStatus


def _build_snapshot() -> MetricsSnapshot:
    return MetricsSnapshot(
        collected_at=datetime.now(timezone.utc),
        namespace="default",
        lookback_minutes=15,
        step="30s",
        metrics={
            "cpu_usage": MetricCollectionResult(
                metric_name="cpu_usage",
                query="sum(rate(container_cpu_usage_seconds_total[5m]))",
                status=SeriesStatus.SUCCESS,
                sample_count=1,
            )
        },
        failed_metrics=[],
        duration_ms=4.2,
    )


def test_collect_metrics_endpoint_returns_snapshot(monkeypatch) -> None:
    """Route should return normalized snapshot from service orchestration."""

    async def fake_collect_metrics(request):
        return _build_snapshot()

    monkeypatch.setattr(routes_module.orchestrator, "collect_metrics", fake_collect_metrics)

    client = TestClient(app)
    response = client.post(
        "/api/v1/metrics/collect",
        json={"namespace": "default", "lookback_minutes": 15, "step": "30s"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["namespace"] == "default"
    assert "cpu_usage" in body["metrics"]


def test_health_endpoint_returns_503_when_prometheus_unhealthy(monkeypatch) -> None:
    """Health route should fail when Prometheus check fails."""

    async def fake_check_health(self):
        return {"healthy": False, "reason": "connection refused"}

    monkeypatch.setattr(routes_module.PrometheusClient, "check_health", fake_check_health)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["status"] == "degraded"

