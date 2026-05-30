
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from app.storage.loki_storage import LokiStorage          # your existing class
from app.models.log_models import LogEntry        # your existing model
from app.agents.log_agent.models.query_logs_input import QueryLogsInput


_QUERY_PATH = "/loki/api/v1/query_range"


def _resolve_time(value: str) -> str:
    """Expand `now` / `now-<N><unit>` shorthands to nanosecond timestamps.

    Loki's HTTP API does not understand relative shorthand — we resolve it
    here so callers (and the LLM) can use natural time expressions.
    """
    if value == "now":
        return str(int(time.time_ns()))
    if value.startswith("now-"):
        suffix = value[4:]
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = suffix[-1]
        amount = int(suffix[:-1])
        return str(int(time.time_ns()) - amount * multipliers[unit] * 1_000_000_000)
    return value  # RFC3339 or raw nanosecond string — pass through unchanged


class LokiService:
    """Unified Loki client: push via LokiStorage, query via httpx.

    Args:
        storage:  Your ``LokiStorage`` instance — owns the base URL and timeout.
        headers:  Extra HTTP headers forwarded to query requests only
                  (e.g. ``{"Authorization": "Bearer <token>"}``).
    """

    def __init__(
        self,
        storage: LokiStorage,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._storage = storage
        self._headers = headers or {}
        # Reuse base_url and timeout directly from LokiStorage — single source of truth.
        self._base_url: str = storage.base_url
        self._timeout: float = storage._timeout

    # ------------------------------------------------------------------
    # Push — fully delegated to LokiStorage
    # ------------------------------------------------------------------

    async def push(self, entries: List[LogEntry]) -> bool:
        """Push log entries to Loki. Delegates entirely to LokiStorage."""
        return await self._storage.push(entries)

    async def push_stream(self, entries_iter) -> int:
        """Batch-push from an iterable. Delegates entirely to LokiStorage."""
        return await self._storage.push_stream(entries_iter)

    async def health_check(self) -> bool:
        """Loki readiness probe. Delegates to LokiStorage."""
        return await self._storage.health_check()

    # ------------------------------------------------------------------
    # Query — thin httpx layer (LokiStorage has no query support)
    # ------------------------------------------------------------------

    async def query_logs(self, params: QueryLogsInput) -> Dict[str, Any]:
        """Run a LogQL query and return the raw Loki JSON response.

        Uses ``query_range`` for both log and metric queries — it is the
        correct endpoint for time-bounded queries regardless of query type.
        """
        http_params: Dict[str, Any] = {
            "query": params.logql_query,
            "start": _resolve_time(params.start),
            "end": _resolve_time(params.end),
            "limit": params.limit,
            "direction": params.direction.value,
        }
        if params.step:
            http_params["step"] = params.step

        url = f"{self._base_url}{_QUERY_PATH}"

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=self._timeout,
        ) as client:
            response = await client.get(url, params=http_params)
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Response formatting (static — no I/O, easy to unit-test)
    # ------------------------------------------------------------------

    @staticmethod
    def format_log_lines(raw: Dict[str, Any]) -> str:
        """Convert a Loki JSON response to human-readable text for the LLM.

        Handles both result types:
        - ``streams``  — raw log lines with timestamps and stream labels.
        - ``matrix``   — metric series (rate/count queries).
        """
        result_type = raw.get("data", {}).get("resultType", "")
        results: List[Any] = raw.get("data", {}).get("result", [])

        if not results:
            return "No log entries found for the given query and time range."

        lines: List[str] = []

        if result_type == "streams":
            for stream in results:
                labels = stream.get("stream", {})
                label_str = ", ".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"[stream: {label_str}]")
                for ts_ns, log_line in stream.get("values", []):
                    ts_s = int(ts_ns) / 1_000_000_000
                    readable_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_s))
                    lines.append(f"  {readable_ts}  {log_line}")

        elif result_type == "matrix":
            for series in results:
                labels = series.get("metric", {})
                label_str = ", ".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"[metric series: {label_str}]")
                for ts_s, value in series.get("values", []):
                    readable_ts = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(float(ts_s)))
                    )
                    lines.append(f"  {readable_ts}  value={value}")
        else:
            return str(raw)

        total = sum(len(s.get("values", [])) for s in results)
        lines.append(f"\n[{total} entries returned]")
        return "\n".join(lines)