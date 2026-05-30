"""Pydantic schemas for Loki log queries."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    """Log line ordering returned by Loki."""

    BACKWARD = "backward"  # newest first (default)
    FORWARD = "forward"    # oldest first


class QueryLogsInput(BaseModel):
    """Parameters for a Loki query_range request.

    Time fields accept three formats (resolved by ``LokiService._resolve_time``):
    - Relative shorthands : ``now``, ``now-15m``, ``now-2h``, ``now-7d``
    - RFC 3339 strings    : ``2024-01-15T12:00:00Z``
    - Raw nanosecond epoch: ``1705316400000000000``
    """

    logql_query: str = Field(
        description=(
            "Valid LogQL expression to execute. "
            "Examples: "
            '`{namespace="prod", app="api"}` — stream selector; '
            '`{app="worker"} |= "ERROR"` — filter pipeline; '
            '`rate({app="api"}[5m])` — metric query.'
        )
    )
    start: str = Field(
        default="now-1h",
        description=(
            "Start of the query time window. "
            "Accepts `now-<N><unit>` (s/m/h/d), RFC 3339, or nanosecond epoch."
        ),
    )
    end: str = Field(
        default="now",
        description=(
            "End of the query time window. "
            "Same format as `start`."
        ),
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Maximum number of log lines / data points to return. Defaults to 100.",
    )
    direction: Direction = Field(
        default=Direction.BACKWARD,
        description='Result ordering: "backward" (newest first) or "forward" (oldest first).',
    )
    step: Optional[str] = Field(
        default=None,
        description=(
            "Resolution step for metric queries, e.g. `30s`, `1m`, `5m`. "
            "Leave unset for plain log stream queries."
        ),
    )