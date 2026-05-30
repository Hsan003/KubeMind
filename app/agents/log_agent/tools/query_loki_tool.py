"""LangChain tool that lets the logs agent query Loki via LokiService."""

from __future__ import annotations

from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.loki_service import LokiService
from app.agents.log_agent.models.query_logs_input import QueryLogsInput


class QueryLokiInput(BaseModel):
    """Input schema for the query_loki tool.

    All time values accept either:
    - relative shorthands  : ``now``, ``now-15m``, ``now-1h``, ``now-2d``
    - RFC 3339 strings     : ``2024-01-15T12:00:00Z``
    - raw nanosecond epoch : ``1705316400000000000``
    """

    logql_query: str = Field(
        description=(
            "A valid LogQL query string. "
            "Examples: "
            '`{namespace="prod", app="api-gateway"}` — stream selector only; '
            '`{app="worker"} |= "ERROR"` — filter for ERROR lines; '
            '`rate({app="api"}[5m])` — metric query.'
        )
    )
    start: str = Field(
        default="now-1h",
        description="Query window start. Accepts `now-<N><unit>` (s/m/h/d), RFC 3339, or nanosecond epoch.",
    )
    end: str = Field(
        default="now",
        description="Query window end. Same format as `start`.",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Maximum number of log lines to return (1–5000). Defaults to 100.",
    )
    direction: str = Field(
        default="backward",
        description='Log ordering: "backward" (newest first) or "forward" (oldest first).',
    )
    step: str | None = Field(
        default=None,
        description=(
            "Resolution step for metric queries (e.g. `30s`, `1m`). "
            "Leave unset for plain log stream queries."
        ),
    )


class QueryLokiTool(BaseTool):
    """LangChain tool wrapping LokiService.query_logs + format_log_lines.

    The agent calls this tool to fetch and read log data from Loki.
    Results are returned as human-readable text so the LLM can reason
    over them directly.

    Usage
    -----
    Instantiate once and pass to the agent's tool list::

        loki_service = LokiService(storage=loki_storage)
        tool = QueryLokiTool(loki_service=loki_service)
    """

    name: str = "query_loki"
    description: str = (
        "Query Grafana Loki for log lines or metric series using LogQL. "
        "Returns formatted log output ready for analysis. "
        "Use this whenever you need to inspect logs, trace errors, check "
        "service health, or count/rate events over a time window."
    )
    args_schema: Type[BaseModel] = QueryLokiInput

    # Pydantic v2 model_config allows arbitrary types (LokiService is not a BaseModel)
    model_config = {"arbitrary_types_allowed": True}

    loki_service: LokiService

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        """Async execution path — preferred by LangChain agents."""
        params = self._build_params(kwargs)
        raw = await self.loki_service.query_logs(params)
        return LokiService.format_log_lines(raw)

    def _run(self, **kwargs: Any) -> str:  # type: ignore[override]
        """Sync fallback (runs the coroutine in a new event loop if needed)."""
        import asyncio

        params = self._build_params(kwargs)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside an existing loop (e.g. Jupyter / FastAPI) — use a thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.loki_service.query_logs(params))
                    raw = future.result()
            else:
                raw = loop.run_until_complete(self.loki_service.query_logs(params))
        except RuntimeError:
            raw = asyncio.run(self.loki_service.query_logs(params))

        return LokiService.format_log_lines(raw)

    @staticmethod
    def _build_params(kwargs: dict[str, Any]) -> QueryLogsInput:
        """Map tool input kwargs → QueryLogsInput, coercing direction to enum."""
        from app.agents.log_agent.models.query_logs_input import Direction  # local import to avoid circular deps

        direction_raw = kwargs.get("direction", "backward")
        try:
            direction = Direction(direction_raw)
        except ValueError:
            direction = Direction.BACKWARD

        return QueryLogsInput(
            logql_query=kwargs["logql_query"],
            start=kwargs.get("start", "now-1h"),
            end=kwargs.get("end", "now"),
            limit=kwargs.get("limit", 100),
            direction=direction,
            step=kwargs.get("step"),
        )