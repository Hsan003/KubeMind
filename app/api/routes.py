"""
FastAPI routes for the incident analyzer API.
"""

from fastapi import APIRouter, HTTPException

from config.settings import settings
from app.ingestion.prometheus_client import PrometheusClient
from app.models.metrics import MetricsCollectionRequest, MetricsSnapshot
from app.services.incident_orchestrator import IncidentOrchestrator

router = APIRouter()
orchestrator = IncidentOrchestrator()


@router.post("/api/v1/metrics/collect", response_model=MetricsSnapshot)
async def collect_metrics(request: MetricsCollectionRequest) -> MetricsSnapshot:
    """Collect Prometheus metrics for Kubernetes incident context."""
    return await orchestrator.collect_metrics(request=request)


@router.get("/health")
async def health_check() -> dict:
    """Health endpoint that validates Prometheus connectivity."""
    async with PrometheusClient(
        base_url=settings.PROMETHEUS_URL,
        timeout_seconds=settings.PROMETHEUS_TIMEOUT_SECONDS,
    ) as prometheus_client:
        health = await prometheus_client.check_health()

    if not health.get("healthy", False):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "prometheus": health,
            },
        )

    return {
        "status": "ok",
        "prometheus": health,
    }
