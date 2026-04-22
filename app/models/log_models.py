from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """A single parsed log line from a Kubernetes pod."""

    namespace: str
    pod_name: str
    container_name: str
    timestamp: datetime
    message: str
    labels: dict[str, str] = Field(default_factory=dict)

    # Optional fields populated during analysis
    log_level: Optional[str] = None   # INFO, WARN, ERROR, DEBUG
    source: str = "kubernetes"


class LogQueryParams(BaseModel):
    """Parameters used to query logs from Kubernetes."""

    namespace: str
    pod_name: Optional[str] = None          # None = all pods in namespace
    container_name: Optional[str] = None
    since_seconds: int = 3600               # default: last hour
    tail_lines: int = 500                   # max lines per pod
    include_previous: bool = False          # include logs from crashed containers


class LokiPushPayload(BaseModel):
    """Loki HTTP push payload shape (for documentation — serialised manually)."""

    # {"streams": [{"stream": {labels}, "values": [[ts_ns_str, line], ...]}]}
    streams: list[dict]