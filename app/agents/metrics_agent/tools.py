"""LangChain tools and schemas for the Metrics Agent."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models.metrics import MetricsCollectionRequest, MetricsSnapshot
from app.services.incident_orchestrator import IncidentOrchestrator


class CollectMetricsToolInput(BaseModel):
    """Input schema for collect_metrics tool calls."""

    namespace: str = Field(default="default", min_length=1)
    workload_name: Optional[str] = None
    workload_kind: Optional[str] = None
    pod_name: Optional[str] = None
    container_name: Optional[str] = None
    lookback_minutes: int = Field(default=15, ge=1, le=1440)
    step: str = Field(default="30s", min_length=2)


class CollectMetricsToolOutput(BaseModel):
    """Output schema emitted by collect_metrics tool."""

    namespace: str
    lookback_minutes: int
    step: str
    metric_statuses: Dict[str, str] = Field(default_factory=dict)
    sample_counts: Dict[str, int] = Field(default_factory=dict)
    failed_metrics: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


def snapshot_to_tool_output(snapshot: MetricsSnapshot) -> CollectMetricsToolOutput:
    """Map full metrics snapshot to compact tool output contract."""
    return CollectMetricsToolOutput(
        namespace=snapshot.namespace,
        lookback_minutes=snapshot.lookback_minutes,
        step=snapshot.step,
        metric_statuses={
            metric_name: metric_result.status.value
            for metric_name, metric_result in snapshot.metrics.items()
        },
        sample_counts={
            metric_name: metric_result.sample_count
            for metric_name, metric_result in snapshot.metrics.items()
        },
        failed_metrics=snapshot.failed_metrics,
        duration_ms=snapshot.duration_ms,
    )


def build_collect_metrics_tool(
    orchestrator: Optional[IncidentOrchestrator] = None,
) -> StructuredTool:
    """Build a structured LangChain tool for Prometheus metric collection."""
    orchestrator = orchestrator or IncidentOrchestrator()

    async def collect_metrics(
        namespace: str = "default",
        workload_name: Optional[str] = None,
        workload_kind: Optional[str] = None,
        pod_name: Optional[str] = None,
        container_name: Optional[str] = None,
        lookback_minutes: int = 15,
        step: str = "30s",
    ) -> Dict[str, Any]:
        request = MetricsCollectionRequest(
            namespace=namespace,
            workload_name=workload_name,
            workload_kind=workload_kind,
            pod_name=pod_name,
            container_name=container_name,
            lookback_minutes=lookback_minutes,
            step=step,
        )
        snapshot = await orchestrator.collect_metrics(request=request)
        output = snapshot_to_tool_output(snapshot)
        return output.model_dump()

    return StructuredTool.from_function(
        coroutine=collect_metrics,
        name="collect_metrics",
        description=(
            "Collect Kubernetes workload metrics from Prometheus for a target scope "
            "and return per-metric status and sample counts."
        ),
        args_schema=CollectMetricsToolInput,
    )
