"""
query_loki — Tool implementation for the Logs Agent
=====================================================
Wraps Loki's HTTP query_range API into a structured tool
the LLM agent can call during incident post-mortem analysis.

Loki HTTP API ref:
  GET /loki/api/v1/query_range
  GET /loki/api/v1/query          (instant)
  GET /loki/api/v1/labels         (label discovery)
  GET /loki/api/v1/series         (series discovery)
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from dataclasses import dataclass, field
# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
from app.agents.log_agent.models.log_stream import LogStream
from app.agents.log_agent.models.log_line import LogLine
from app.agents.log_agent.models.query_stats import QueryStats
from app.agents.log_agent.models.loki_result import LokiResult

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class LokiConfig:
    base_url: str = field(
        default_factory=lambda: os.environ.get("LOKI_BASE_URL", "http://localhost:3100")
    )
    auth_token: Optional[str] = field(
        default_factory=lambda: os.environ.get("LOKI_AUTH_TOKEN")
    )
    org_id: Optional[str] = field(
        default_factory=lambda: os.environ.get("LOKI_ORG_ID")          # multi-tenant
    )
    timeout_s: float = 30.0
    max_retries: int = 3
    retry_backoff_s: float = 1.0



# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LokiClient:
    """Thin async HTTP client around Loki's query API."""

    def __init__(self, config: Optional[LokiConfig] = None):
        self.config = config or LokiConfig()
        self._headers = self._build_headers()

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        if self.config.org_id:
            headers["X-Scope-OrgID"] = self.config.org_id
        return headers

    def _parse_iso(self, ts: str) -> str:
        """Accept ISO-8601 or Unix-ns strings → Unix nanoseconds for Loki."""
        try:
            # Already a unix timestamp (int or float as string)
            float(ts)
            return ts
        except ValueError:
            pass
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1_000_000_000))

    def _ns_to_iso(self, ns: str) -> str:
        seconds = int(ns) / 1_000_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()

    def _humanise_bytes(self, n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f}{unit}"
            n //= 1024
        return f"{n:.1f}TB"

    def _parse_response(
        self, raw: dict, exec_ms: int
    ) -> LokiResult:
        data = raw.get("data", {})
        result_type = data.get("resultType", "streams")
        results = data.get("result", [])

        streams: list[LogStream] = []
        total_lines = 0

        for stream_data in results:
            labels = stream_data.get("stream", {})
            values = stream_data.get("values", [])      # [[ns, msg], ...]
            lines = []
            for ns, msg in values:
                lines.append(LogLine(
                    timestamp_ns=ns,
                    timestamp_iso=self._ns_to_iso(ns),
                    message=msg,
                    stream_labels=labels,
                ))
            total_lines += len(lines)
            streams.append(LogStream(labels=labels, lines=lines))

        # Loki stats block (may be absent in older versions)
        loki_stats = data.get("stats", {})
        ingester_stats = loki_stats.get("ingester", {})
        store_stats = loki_stats.get("store", {})
        bytes_proc = (
            ingester_stats.get("totalDecompressedBytes", 0)
            + store_stats.get("decompressedBytes", 0)
        )

        return LokiResult(
            status="success",
            result_type=result_type,
            streams=streams,
            stats=QueryStats(
                lines_returned=total_lines,
                streams_count=len(streams),
                bytes_processed=self._humanise_bytes(bytes_proc),
                exec_time_ms=exec_ms,
            ),
            raw_response=raw,
        )

    def query_range(
        self,
        logql_query: str,
        start_time: str,
        end_time: str,
        limit: int = 200,
        direction: Literal["forward", "backward"] = "backward",
        step: Optional[str] = None,
    ) -> LokiResult:
        """
        Execute a range query against Loki (sync, with retry).
        Maps to: GET /loki/api/v1/query_range
        """
        params: dict[str, Any] = {
            "query": logql_query,
            "start": self._parse_iso(start_time),
            "end":   self._parse_iso(end_time),
            "limit": limit,
            "direction": direction,
        }
        if step:
            params["step"] = step

        url = f"{self.config.base_url}/loki/api/v1/query_range"
        last_err: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                t0 = time.perf_counter()
                with httpx.Client(
                    headers=self._headers,
                    timeout=self.config.timeout_s,
                ) as client:
                    resp = client.get(url, params=params)

                exec_ms = int((time.perf_counter() - t0) * 1000)

                if resp.status_code == 200:
                    return self._parse_response(resp.json(), exec_ms)

                # Loki surfaces errors in the JSON body
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("message", resp.text)
                except Exception:
                    err_msg = resp.text

                logger.warning(
                    "Loki query failed (attempt %d/%d): HTTP %d — %s",
                    attempt, self.config.max_retries, resp.status_code, err_msg,
                )
                # 4xx errors are not retryable
                if 400 <= resp.status_code < 500:
                    return LokiResult(
                        status="error",
                        result_type="streams",
                        streams=[],
                        stats=QueryStats(0, 0, "0B", exec_ms),
                        error=f"HTTP {resp.status_code}: {err_msg}",
                    )
                last_err = RuntimeError(f"HTTP {resp.status_code}: {err_msg}")

            except httpx.TimeoutException as e:
                last_err = e
                logger.warning("Loki timeout (attempt %d/%d)", attempt, self.config.max_retries)
            except httpx.RequestError as e:
                last_err = e
                logger.warning("Loki request error (attempt %d/%d): %s", attempt, self.config.max_retries, e)

            if attempt < self.config.max_retries:
                time.sleep(self.config.retry_backoff_s * attempt)

        return LokiResult(
            status="error",
            result_type="streams",
            streams=[],
            stats=QueryStats(0, 0, "0B", 0),
            error=str(last_err),
        )

    def instant_query(
        self,
        logql_query: str,
        at_time: Optional[str] = None,
        limit: int = 100,
        direction: Literal["forward", "backward"] = "backward",
    ) -> LokiResult:
        """
        Single-point query (no range).
        Maps to: GET /loki/api/v1/query
        """
        params: dict[str, Any] = {
            "query": logql_query,
            "limit": limit,
            "direction": direction,
        }
        if at_time:
            params["time"] = self._parse_iso(at_time)

        url = f"{self.config.base_url}/loki/api/v1/query"
        t0 = time.perf_counter()
        try:
            with httpx.Client(headers=self._headers, timeout=self.config.timeout_s) as client:
                resp = client.get(url, params=params)
            exec_ms = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                return self._parse_response(resp.json(), exec_ms)
            return LokiResult(
                status="error", result_type="streams", streams=[],
                stats=QueryStats(0, 0, "0B", exec_ms),
                error=f"HTTP {resp.status_code}: {resp.text}",
            )
        except Exception as e:
            return LokiResult(
                status="error", result_type="streams", streams=[],
                stats=QueryStats(0, 0, "0B", 0),
                error=str(e),
            )

    def list_labels(self) -> list[str]:
        """Discover available label names — useful for the agent to build queries."""
        url = f"{self.config.base_url}/loki/api/v1/labels"
        try:
            with httpx.Client(headers=self._headers, timeout=10.0) as client:
                resp = client.get(url)
            if resp.status_code == 200:
                return resp.json().get("data", [])
        except Exception as e:
            logger.error("Failed to fetch Loki labels: %s", e)
        return []


# ---------------------------------------------------------------------------
# Tool function — this is what the agent framework calls
# ---------------------------------------------------------------------------

# Singleton client (one connection pool per process)
_client: Optional[LokiClient] = None

def _get_client() -> LokiClient:
    global _client
    if _client is None:
        _client = LokiClient()
    return _client


def query_loki(
    logql_query: str,
    start_time: str,
    end_time: str,
    limit: int = 200,
    direction: Literal["forward", "backward"] = "backward",
    step: Optional[str] = None,
) -> dict[str, Any]:
    """
    Tool entry point called by the Logs Agent LLM.

    Args:
        logql_query:  LogQL selector + filter, e.g.
                      '{namespace="prod",app="api"} |= "error" | level="error"'
        start_time:   ISO-8601 UTC start, e.g. "2024-03-15T14:00:00Z"
        end_time:     ISO-8601 UTC end,   e.g. "2024-03-15T14:30:00Z"
        limit:        Max lines to return (default 200, max 5000)
        direction:    "backward" (newest first) | "forward" (oldest first)
        step:         Metric query resolution, e.g. "30s" or "1m"

    Returns:
        dict suitable for injection back into the LLM message context.
    """
    logger.info(
        "query_loki called | query=%s start=%s end=%s limit=%d",
        logql_query, start_time, end_time, limit,
    )

    # Guard: cap limit so the agent can't blow the context window
    limit = min(limit, 5000)

    result = _get_client().query_range(
        logql_query=logql_query,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        direction=direction,
        step=step,
    )

    agent_dict = result.to_agent_dict()
    logger.info(
        "query_loki done | status=%s lines=%s exec_ms=%s",
        agent_dict["status"],
        agent_dict.get("stats", {}).get("lines_returned", "—"),
        agent_dict.get("stats", {}).get("exec_ms", "—"),
    )
    return agent_dict


# ---------------------------------------------------------------------------
# Tool schema (passed to the LLM at agent construction time)
# ---------------------------------------------------------------------------

TOOL_SCHEMA: dict[str, Any] = {
    "name": "query_loki",
    "description": (
        "Query the Loki log aggregation database using LogQL. "
        "Use this to retrieve log lines during incident post-mortem analysis — "
        "surface error bursts, exception traces, service failures, and timing anomalies. "
        "Prefer narrow time windows and specific label selectors to keep results focused."
    ),
    "input_schema": {
        "type": "object",
        "required": ["logql_query", "start_time", "end_time"],
        "properties": {
            "logql_query": {
                "type": "string",
                "description": (
                    "LogQL stream selector + optional filter pipeline. "
                    "Examples:\n"
                    "  '{namespace=\"prod\",app=\"api\"} |= \"error\"'\n"
                    "  '{app=\"payment-svc\"} | json | level=\"error\" | duration > 2s'\n"
                    "  'rate({app=\"api\"}[5m])'"
                ),
            },
            "start_time": {
                "type": "string",
                "description": "ISO-8601 UTC timestamp for the start of the query window. E.g. '2024-03-15T14:00:00Z'",
            },
            "end_time": {
                "type": "string",
                "description": "ISO-8601 UTC timestamp for the end of the query window. E.g. '2024-03-15T14:30:00Z'",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of log lines to return. Default 200. Max 5000. Use smaller values first.",
                "default": 200,
            },
            "direction": {
                "type": "string",
                "enum": ["forward", "backward"],
                "description": "'backward' returns newest lines first (default). 'forward' returns oldest first.",
                "default": "backward",
            },
            "step": {
                "type": "string",
                "description": "Resolution step for metric queries only (e.g. '30s', '1m'). Omit for log stream queries.",
            },
        },
    },
}