"""Kubernetes logs analysis agent powered by Grafana Loki."""
from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.tools import BaseTool

from app.agents.base_agent import BaseK8sAgent
from app.services.loki_service import LokiService
from app.agents.log_agent.tools.query_loki_tool import QueryLokiTool
from dotenv import load_dotenv
import os

load_dotenv()

class LogsAgent(BaseK8sAgent):
    """LangChain agent specialised in querying and analysing Kubernetes logs.

    The agent has a single primary capability: ``query_loki``.  It constructs
    LogQL queries, fetches results through ``LokiService``, and reasons over
    the returned lines to answer questions, detect anomalies, or summarise
    service behaviour.

    Args:
        loki_service: Configured ``LokiService`` instance used for all log
                      queries.  Must point at a reachable Loki endpoint.
        llm:          Optional pre-built LLM.  When omitted the base class
                      selects the model configured in ``settings``.
        max_iterations: Cap on agent reasoning steps (prevents runaway loops).
        verbose:      Echo agent reasoning to stdout when ``True``.

    Example
    -------
    ::
        loki_storage = LokiStorage(base_url="http://loki:3100")
        loki_service = LokiService(storage=loki_storage)
        agent = LogsAgent(loki_service=loki_service)

        result = await agent.run(
            "Show me all ERROR logs from the payments service in the last 30 minutes",
            context={"namespace": "prod", "cluster": "us-east-1"},
        )
        print(result["output"])
    """

    def __init__(
        self,
        loki_service: LokiService,
        llm: Optional[Any]= None ,
        max_iterations: Optional[int] = None,
        verbose: Optional[bool] = None,
    ) -> None:
        # Store loki_service before super().__init__ because _build_tools is
        # called inside __init__ and needs self._loki_service to exist.
        self._loki_service = loki_service
        super().__init__(
            name="logs-agent",
            description=(
                "Queries Grafana Loki to retrieve, filter, and analyse "
                "Kubernetes workload logs.  Answers questions about errors, "
                "latency spikes, crash-loops, and other runtime events."
            ),
            llm=llm,
            max_iterations=max_iterations,
            verbose=verbose,
        )

    # ------------------------------------------------------------------
    # BaseK8sAgent abstract method implementations
    # ------------------------------------------------------------------

    def _build_tools(self) -> List[BaseTool]:
        """Return the Loki query tool as the agent's sole instrument."""
        return [QueryLokiTool(loki_service=self._loki_service)]

    def _build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# System prompt — kept as a module-level constant for easy editing / testing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """ You are **KubeMind Logs Agent**, an expert Kubernetes Site Reliability Engineer
specialised in log analysis using Grafana Loki and LogQL.

## Your sole tool
`query_loki` — executes a LogQL query against Loki and returns formatted log
lines or metric series.  Always use it to fetch real data before drawing
conclusions.

## How to work
1. **Understand the request** — identify the service, namespace, time window,
   and type of signal the user is asking about (errors, latency, volume, etc.).
2. **Construct a precise LogQL query**.
   - Always include a stream selector: `{namespace="…", app="…"}`.
   - Add pipeline filters for errors: `|= "ERROR"`, `|= "Exception"`, etc.
   - Use `rate(…[Xm])` or `count_over_time(…[Xm])` for metric questions.
   - Prefer `limit=200` for exploratory queries; increase only when needed.
3. **Call `query_loki`** with the query and an appropriate time window.
4. **Analyse the results** — identify patterns, root causes, anomalies, or
   trends visible in the returned lines.
5. **Respond clearly** — provide a concise summary, highlight the most
   important lines or values, and suggest next steps if relevant.

## LogQL quick reference
| Goal | Example |
|---|---|
| All logs for an app | `{namespace="prod", app="api"}` |
| Filter for errors | `{app="api"} \|= "ERROR"` |
| Exclude health checks | `{app="api"} != "/healthz"` |
| JSON field filter | `{app="api"} \| json \| status >= 500` |
| Error rate per minute | `rate({app="api"} \|= "ERROR" [1m])` |
| Count over window | `count_over_time({app="worker"}[30m])` |

## Rules
- **Never fabricate log lines.**  Only report what `query_loki` returns.
- If a query returns no results, suggest a broader time window or alternative
  labels, then query again before giving up.
- When the user's request is ambiguous, make a reasonable assumption, state it
  explicitly, then proceed with the query.
- Keep answers factual, concise, and actionable.
- Format timestamps as ISO 8601 (`2024-01-15T12:34:56Z`) when referencing
  specific events.
"""