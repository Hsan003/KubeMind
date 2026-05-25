"""
Incident orchestrator - orchestrates analysis across all agents.
"""

from __future__ import annotations

from typing import Optional

from config.settings import settings
from app.ingestion.metrics_collector import MetricsCollector
from app.ingestion.prometheus_client import PrometheusClient
from app.models.metrics import MetricsCollectionRequest, MetricsSnapshot


class IncidentOrchestrator:
    """Service layer orchestrating metrics collection for incident context."""

    async def collect_metrics(
        self,
        request: MetricsCollectionRequest,
    ) -> MetricsSnapshot:
        """Collect and normalize metrics using Prometheus-backed collector."""
        async with PrometheusClient(
            base_url=settings.PROMETHEUS_URL,
            timeout_seconds=settings.PROMETHEUS_TIMEOUT_SECONDS,
        ) as prometheus_client:
            collector = MetricsCollector(prometheus_client=prometheus_client)
            return await collector.collect(request=request)

    async def collect_metrics_from_filters(
        self,
        namespace: Optional[str] = None,
        workload_name: Optional[str] = None,
        workload_kind: Optional[str] = None,
        pod_name: Optional[str] = None,
        container_name: Optional[str] = None,
        lookback_minutes: Optional[int] = None,
        step: Optional[str] = None,
    ) -> MetricsSnapshot:
        """Build request object from route payload and run collection."""
        request = MetricsCollectionRequest(
            namespace=namespace or settings.NAMESPACE,
            workload_name=workload_name,
            workload_kind=workload_kind,
            pod_name=pod_name,
            container_name=container_name,
            lookback_minutes=lookback_minutes or settings.PROMETHEUS_DEFAULT_LOOKBACK_MINUTES,
            step=step or settings.PROMETHEUS_DEFAULT_STEP,
        )
        return await self.collect_metrics(request=request)