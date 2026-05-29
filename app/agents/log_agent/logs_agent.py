"""
logs_agent.py — LangChain-powered Logs Agent
=============================================
Sits in the AI Agents Layer (see architecture).

Responsibilities
----------------
  1. Accept an investigation request (incident window + context).
  2. Iteratively call query_loki to surface errors, traces, and anomalies.
  3. Return a structured LogsReport to the Correlation Agent.

Dependencies
------------
  pip install langchain-core langchain-anthropic langgraph pydantic httpx
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

# ── LangChain / LangGraph v0.3+ correct import paths ────────────────────────
from langchain_core.tools import StructuredTool          # NOT langchain.tools
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent        # replaces AgentExecutor + create_tool_calling_agent
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Local import — the tool we already built
# ---------------------------------------------------------------------------
from app.agents.log_agent.tools.loki_tool import query_loki, TOOL_SCHEMA, LokiConfig, LokiClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / Output schemas (shared with the Correlation Agent)
# ---------------------------------------------------------------------------

class InvestigationRequest(BaseModel):
    """Payload sent TO the Logs Agent by an orchestrator / Correlation Agent."""

    incident_id: str = Field(..., description="Unique incident identifier")
    start_time: str = Field(..., description="ISO-8601 UTC start of the incident window")
    end_time: str = Field(..., description="ISO-8601 UTC end of the incident window")
    affected_services: list[str] = Field(
        default_factory=list,
        description="Kubernetes service / app labels known to be affected",
    )
    namespace: str = Field(default="prod", description="Kubernetes namespace to scope queries")
    hypothesis: Optional[str] = Field(
        None,
        description="Optional free-text hint from the operator or upstream agent",
    )
    max_iterations: int = Field(
        default=8,
        description="Max LLM reasoning steps before the agent is forced to conclude",
    )


class LogAnomaly(BaseModel):
    """A single noteworthy finding extracted from logs."""

    service: str
    severity: str                  # "critical" | "error" | "warning" | "info"
    first_seen: str                # ISO-8601
    last_seen: str                 # ISO-8601
    count: int
    pattern: str                   # Short description of the log pattern
    sample_message: str            # Representative log line
    logql_query: str               # The query that surfaced it


class LogsReport(BaseModel):
    """Structured report returned TO the Correlation Agent."""

    incident_id: str
    analysis_time_utc: str
    time_window: dict[str, str]    # {"start": ..., "end": ...}
    summary: str                   # 2-3 sentence executive summary
    anomalies: list[LogAnomaly]
    root_cause_hypothesis: str     # Agent's best guess
    recommended_queries: list[str] # LogQL queries for deeper drill-down   probably ni7ihom
    raw_tool_calls: list[dict]     # Audit trail of every query_loki call


# ---------------------------------------------------------------------------
# Pydantic input model for the LangChain StructuredTool
# ---------------------------------------------------------------------------

class QueryLokiInput(BaseModel):
    logql_query: str = Field(..., description=TOOL_SCHEMA["input_schema"]["properties"]["logql_query"]["description"])
    start_time: str = Field(..., description="ISO-8601 UTC start")
    end_time: str = Field(..., description="ISO-8601 UTC end")
    limit: int = Field(200, description="Max lines to return (max 5000)")
    direction: str = Field("backward", description="'backward' or 'forward'")
    step: Optional[str] = Field(None, description="Step for metric queries, e.g. '30s'")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the **Logs Agent**, a specialist AI in a Kubernetes observability pipeline.

## Your mission
Analyse application and infrastructure logs from a Loki log database to investigate
incidents, surface root causes, and produce a structured report for the Correlation Agent.

## Tools
You have one tool: `query_loki`.

### Strategy — work in this order
1. **Orient**: query broad error selectors for each affected service in the incident window.
2. **Triage**: identify the services with the highest error rate / novel error patterns.
3. **Drill down**: narrow queries by time, log level, or specific error keywords.
4. **Trace**: look for exception stack traces, timeouts, OOM events, or panic messages.
5. **Timeline**: reconstruct when errors first appeared vs when the incident was declared.
6. **Conclude**: write your final JSON report.

### LogQL tips
- Always scope with namespace and app labels: {{namespace="{namespace}",app="svc"}}
- Filter errors first: |= "error" or | json | level="error"
- For latency: | json | duration > 2s
- For stack traces: |~ "Exception|Traceback|panic"
- Keep limit <= 500 per call; make multiple focused calls rather than one huge one.

## Output format
When you have enough evidence, respond with ONLY a JSON object (no markdown fences):

{{
  "incident_id": "...",
  "analysis_time_utc": "<ISO-8601>",
  "time_window": {{"start": "...", "end": "..."}},
  "summary": "...",
  "anomalies": [
    {{
      "service": "...",
      "severity": "critical|error|warning|info",
      "first_seen": "...",
      "last_seen": "...",
      "count": 0,
      "pattern": "...",
      "sample_message": "...",
      "logql_query": "..."
    }}
  ],
  "root_cause_hypothesis": "...",
  "recommended_queries": ["..."],
  "raw_tool_calls": []
}}

Current UTC time: {current_time}
Incident window: {start_time} -> {end_time}
Namespace: {namespace}
Affected services: {affected_services}
Hypothesis: {hypothesis}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class LogsAgent:
    """
    LangGraph-based agent that investigates incidents via Loki.

    Usage
    -----
    agent = LogsAgent()
    report: LogsReport = agent.run(request)
    """

    def __init__(
        self,
        model: str = "claude-opus-4-5",
        loki_config: Optional[LokiConfig] = None,
        temperature: float = 0.0,
    ):
        self.loki_config = loki_config or LokiConfig()
        self._tool_call_log: list[dict] = []

        # ── LLM ──────────────────────────────────────────────────────────────
        self.llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=4096,
        )

        # ── Tool ─────────────────────────────────────────────────────────────
        self.loki_tool = StructuredTool.from_function(
            func=self._instrumented_query_loki,
            name="query_loki",
            description=TOOL_SCHEMA["description"],
            args_schema=QueryLokiInput,
        )

        # ── Agent (LangGraph prebuilt ReAct — v0.3+ recommended pattern) ────
        # System prompt is injected per-run via the messages list so it carries
        # incident-specific context (window, namespace, hypothesis).
        self.agent = create_react_agent(
            model=self.llm,
            tools=[self.loki_tool],
        )

    # ── Internal instrumented wrapper ────────────────────────────────────────

    def _instrumented_query_loki(
        self,
        logql_query: str,
        start_time: str,
        end_time: str,
        limit: int = 200,
        direction: str = "backward",
        step: Optional[str] = None,
    ) -> dict[str, Any]:
        """Thin wrapper that records every call for the audit trail."""
        result = query_loki(
            logql_query=logql_query,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            direction=direction,
            step=step,
        )
        self._tool_call_log.append({
            "logql_query": logql_query,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "direction": direction,
            "step": step,
            "result_status": result.get("status"),
            "lines_returned": result.get("stats", {}).get("lines_returned", 0),
        })
        return result

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self, request: InvestigationRequest) -> LogsReport:
        """
        Investigate an incident and return a structured LogsReport.

        Parameters
        ----------
        request : InvestigationRequest
            The investigation task from the orchestrator / Correlation Agent.

        Returns
        -------
        LogsReport
            Structured findings ready for the Correlation Agent to consume.
        """
        self._tool_call_log = []  # reset per run

        system_prompt = SYSTEM_PROMPT.format(
            current_time=datetime.now(timezone.utc).isoformat(),
            start_time=request.start_time,
            end_time=request.end_time,
            namespace=request.namespace,
            affected_services=", ".join(request.affected_services) or "unknown (discover via labels)",
            hypothesis=request.hypothesis or "none provided",
        )

        human_message = (
            f"Incident ID: {request.incident_id}\n"
            f"Please investigate the incident between {request.start_time} and {request.end_time}.\n"
            f"Namespace: {request.namespace}\n"
            f"Affected services: {', '.join(request.affected_services) or 'unknown'}\n"
            f"Hypothesis: {request.hypothesis or 'none'}\n\n"
            "Begin your investigation. When done, produce the final JSON report."
        )

        logger.info("LogsAgent starting investigation for incident %s", request.incident_id)

        # LangGraph agents take a plain messages list — system prompt goes first
        result = self.agent.invoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_message),
                ]
            },
            config={"recursion_limit": request.max_iterations * 2},  # each tool call = 2 steps
        )

        # Last message in the thread is the final AI response
        raw_output: str = result["messages"][-1].content
        return self._parse_report(raw_output, request)

    # ── Output parsing ───────────────────────────────────────────────────────

    def _parse_report(self, raw_output: str, request: InvestigationRequest) -> LogsReport:
        """
        Parse the agent's final JSON output into a validated LogsReport.
        Falls back to a minimal report on parse failure.
        """
        # Strip accidental markdown fences
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                l for l in lines if not l.startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)
            data["raw_tool_calls"] = self._tool_call_log
            data.setdefault("incident_id", request.incident_id)
            data.setdefault(
                "analysis_time_utc",
                datetime.now(timezone.utc).isoformat(),
            )
            return LogsReport(**data)

        except (json.JSONDecodeError, Exception) as exc:
            logger.error("Failed to parse LogsReport JSON: %s", exc)
            logger.debug("Raw agent output:\n%s", raw_output)

            return LogsReport(
                incident_id=request.incident_id,
                analysis_time_utc=datetime.now(timezone.utc).isoformat(),
                time_window={"start": request.start_time, "end": request.end_time},
                summary=raw_output[:500],
                anomalies=[],
                root_cause_hypothesis="Parse error — see summary for raw agent output.",
                recommended_queries=[],
                raw_tool_calls=self._tool_call_log,
            )