"""Tests for MetricsAgent tool schemas and runtime behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents.base_agent import BaseK8sAgent
from app.agents.metrics_agent import MetricsAgent
from app.agents.metrics_agent.tools import (
    CollectMetricsToolInput,
    build_collect_metrics_tool,
    snapshot_to_tool_output,
)
from app.models.metrics import (
    MetricCollectionResult,
    MetricPoint,
    MetricSeries,
    MetricsSnapshot,
    SeriesStatus,
)


def _build_snapshot() -> MetricsSnapshot:
    """Build a deterministic sample snapshot for tests."""
    return MetricsSnapshot(
        namespace="default",
        lookback_minutes=15,
        step="30s",
        metrics={
            "cpu_usage": MetricCollectionResult(
                metric_name="cpu_usage",
                query="sum(rate(container_cpu_usage_seconds_total[5m]))",
                status=SeriesStatus.SUCCESS,
                sample_count=1,
                series=[
                    MetricSeries(
                        metric_name="cpu_usage",
                        query="sum(rate(container_cpu_usage_seconds_total[5m]))",
                        labels={"namespace": "default", "pod": "api-1"},
                        points=[
                            MetricPoint(
                                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                                value=0.15,
                            )
                        ],
                        status=SeriesStatus.SUCCESS,
                    )
                ],
            )
        },
        failed_metrics=[],
        duration_ms=7.5,
    )


def test_collect_metrics_tool_input_schema_validation() -> None:
    """Input schema should enforce basic validation constraints."""
    with pytest.raises(ValidationError):
        CollectMetricsToolInput(namespace="")


def test_snapshot_to_tool_output_contract() -> None:
    """Snapshot conversion should expose compact status/sample summaries."""
    output = snapshot_to_tool_output(_build_snapshot())
    assert output.namespace == "default"
    assert output.metric_statuses["cpu_usage"] == "success"
    assert output.sample_counts["cpu_usage"] == 1
    assert output.failed_metrics == []


@pytest.mark.asyncio
async def test_collect_metrics_tool_execution() -> None:
    """Structured tool should call orchestrator and return schema-shaped payload."""

    class FakeOrchestrator:
        async def collect_metrics(self, request):  # type: ignore[no-untyped-def]
            assert request.namespace == "default"
            return _build_snapshot()

    tool = build_collect_metrics_tool(orchestrator=FakeOrchestrator())
    result = await tool.ainvoke({"namespace": "default", "lookback_minutes": 15, "step": "30s"})

    assert result["namespace"] == "default"
    assert result["metric_statuses"]["cpu_usage"] == "success"
    assert result["sample_counts"]["cpu_usage"] == 1


@pytest.mark.asyncio
async def test_metrics_agent_analyze_metrics_returns_executor_output(monkeypatch) -> None:
    """MetricsAgent should route analysis through BaseK8sAgent.run()."""

    class FakeExecutor:
        async def ainvoke(self, payload):  # type: ignore[no-untyped-def]
            assert "messages" in payload
            return {
                "messages": [
                    type(
                        "FakeAiMessage",
                        (),
                        {"type": "ai", "content": "healthy", "tool_calls": []},
                    )()
                ]
            }

    monkeypatch.setattr(BaseK8sAgent, "_build_executor", lambda self: FakeExecutor())

    class FakeOrchestrator:
        async def collect_metrics(self, request):  # type: ignore[no-untyped-def]
            return _build_snapshot()

    agent = MetricsAgent(orchestrator=FakeOrchestrator(), llm=object())
    response = await agent.analyze_metrics("Assess current metrics health", scope={"namespace": "default"})

    assert response["agent_name"] == "metrics_agent"
    assert response["output"] == "healthy"
    assert response["context"]["namespace"] == "default"
