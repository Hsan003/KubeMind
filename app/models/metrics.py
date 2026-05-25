"""Pydantic models for metrics collection and normalization."""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SeriesStatus(str, Enum):
    """Normalized status for each metric series."""

    SUCCESS = "success"
    EMPTY = "empty"
    ERROR = "error"


class MetricsCollectionRequest(BaseModel):
    """Input payload for collecting metrics from Prometheus."""

    namespace: str = Field(default="default", min_length=1)
    workload_name: Optional[str] = Field(default=None)
    workload_kind: Optional[str] = Field(default=None)
    pod_name: Optional[str] = Field(default=None)
    container_name: Optional[str] = Field(default=None)
    lookback_minutes: int = Field(default=15, ge=1, le=1440)
    step: str = Field(default="30s", min_length=2)


class MetricPoint(BaseModel):
    """Single normalized datapoint from a Prometheus series."""

    timestamp: datetime
    value: float


class MetricSeries(BaseModel):
    """One metric series after normalization."""

    metric_name: str
    query: str
    labels: Dict[str, str] = Field(default_factory=dict)
    points: List[MetricPoint] = Field(default_factory=list)
    status: SeriesStatus = SeriesStatus.SUCCESS
    error: Optional[str] = None


class MetricCollectionResult(BaseModel):
    """Grouped result for one metric query."""

    metric_name: str
    query: str
    status: SeriesStatus
    series: List[MetricSeries] = Field(default_factory=list)
    sample_count: int = 0
    error: Optional[str] = None


class MetricsSnapshot(BaseModel):
    """Output payload returned by the metrics collector workflow."""

    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    namespace: str
    lookback_minutes: int
    step: str
    metrics: Dict[str, MetricCollectionResult] = Field(default_factory=dict)
    failed_metrics: List[str] = Field(default_factory=list)
    duration_ms: float = 0.0

