from datetime import datetime, timezone
from typing import Any, Literal, Optional
from dataclasses import dataclass, field

from app.agents.log_agent.models.log_stream import LogStream
from app.agents.log_agent.models.query_stats import QueryStats

@dataclass

class LokiResult:
    status: Literal["success", "error"]
    result_type: Literal["streams", "matrix", "vector", "scalar"]
    streams: list[LogStream]
    stats: QueryStats
    error: Optional[str] = None
    raw_response: Optional[dict] = None

    def to_agent_dict(self) -> dict[str, Any]:
        """Compact representation optimised for LLM context window."""
        if self.status == "error":
            return {"status": "error", "error": self.error}

        return {
            "status": "success",
            "result_type": self.result_type,
            "stats": {
                "lines_returned": self.stats.lines_returned,
                "streams": self.stats.streams_count,
                "bytes_processed": self.stats.bytes_processed,
                "exec_ms": self.stats.exec_time_ms,
            },
            "streams": [
                {
                    "labels": s.labels,
                    "lines": [
                        {"ts": l.timestamp_iso, "msg": l.message}
                        for l in s.lines
                    ],
                }
                for s in self.streams
            ],
        }
