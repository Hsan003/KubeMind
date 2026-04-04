from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

class LogSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class PodLog(BaseModel):
    pod_name: str
    namespace: str
    container: str
    timestamp: datetime
    raw_message: str
    severity: LogSeverity = LogSeverity.INFO
    labels: dict = Field(default_factory=dict)

class EnrichedLog(PodLog):
    cluster_name: str
    error_patterns: list[str] = Field(default_factory=list)
    ingestion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ingested_at: datetime = Field(default_factory=datetime.utcnow)