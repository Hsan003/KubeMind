"""Base agent class for all KubeMind specialized agents.

This module owns ALL model/LLM logic. Subclasses are pure configuration:
they declare their tools, their domain-specific prompt focus, and how
to serialize their input into a plain string. The model call, ReAct
loop, JSON parsing, lifecycle orchestration, and result construction
all happen here — children never touch the LLM directly.

Subclasses MUST declare (as class attributes or properties):
  - name         (str)            - agent identifier, e.g. "log_agent"
  - description  (str)            - one-line human-readable purpose
  - focus        (str)            - one short paragraph telling the LLM
                                    *what to look for* in this domain.
                                    Kept intentionally narrow so the agent
                                    is not distracted by other concerns.
  - agent_tools  (List[BaseTool]) - domain-specific LangChain tools

Subclasses MAY override:
  - preprocess(data)   - normalize/truncate raw input  (default: pass-through)
  - postprocess(result)- clean/enrich the result        (default: pass-through)
  - format_input(data) - serialize data dict to the prompt string
                         (default: JSON dump of the data dict)
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import BaseTool, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.models.analysis import AnalysisResult, SeverityLevel
from app.utils.logger import setup_logger


# ---------------------------------------------------------------------------
# Shared tools — available to every agent regardless of domain
# ---------------------------------------------------------------------------

@tool
def get_current_utc_time() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Useful when a finding needs to be timestamped or when calculating
    how long ago an event occurred.
    """
    return datetime.now(timezone.utc).isoformat()


@tool
def classify_severity(description: str) -> str:
    """Heuristically classify the severity of an issue from a plain-text description.

    Use this as a cross-check against your own reasoning.

    Args:
        description: Short description of the observed problem.

    Returns:
        One of: critical | high | medium | low | info
    """
    low = description.lower()
    if any(kw in low for kw in ("crash", "oom", "killed", "evicted", "panic", "down", "unavailable")):
        return SeverityLevel.CRITICAL.value
    if any(kw in low for kw in ("error", "fail", "timeout", "restart", "backoff", "refused")):
        return SeverityLevel.HIGH.value
    if any(kw in low for kw in ("warn", "slow", "throttl", "limit", "pending", "delay")):
        return SeverityLevel.MEDIUM.value
    if any(kw in low for kw in ("info", "debug", "notice", "started", "ok")):
        return SeverityLevel.INFO.value
    return SeverityLevel.LOW.value


# Tools injected into every agent (on top of domain-specific ones)
SHARED_TOOLS: List[BaseTool] = [get_current_utc_time, classify_severity]


# ---------------------------------------------------------------------------
# Base system prompt — intentionally generic, domain-agnostic
#
# The only domain knowledge injected per-agent is the short `focus` paragraph
# (what to look for). Everything else — rules, output format, ReAct syntax —
# lives here once and is never duplicated in children.
# ---------------------------------------------------------------------------

_BASE_PROMPT_TEMPLATE = """\
You are KubeMind, an AI-powered Kubernetes incident analyst.

Your task is to analyze the data provided and return structured findings.

## Rules
- Base every conclusion strictly on the data given. Do not invent values.
- Severity scale: critical (service down) | high (major degradation) | \
medium (partial impact) | low (minor issue) | info (no impact).
- Each finding must state: what happened, why it matters, what to check next.
- Be concise: one to three sentences per finding.
- If the data is insufficient, say so explicitly rather than guessing.

## Your focus for this analysis
{focus}

## Required output format
Respond with a single JSON object — no markdown fences, no extra text:
{{
  "findings"  : ["<finding 1>", "<finding 2>", ...],
  "severity"  : "<critical|high|medium|low|info>",
  "confidence": <float 0-1>,
  "summary"   : "<one-line summary>"
}}

## Available tools
{tools}

## Scratchpad (ReAct format)
Use tools when they help you reach a conclusion. Format:
Thought: <your reasoning>
Action: <tool name>
Action Input: <tool input>
Observation: <tool output>
... repeat as needed ...
Thought: I now have enough information.
Final Answer: <JSON object>

{agent_scratchpad}"""


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all KubeMind analysis agents.

    Owns the full LLM lifecycle: building the ReAct executor, calling the
    model, parsing the JSON response, and producing an AnalysisResult.

    Children only need to declare:
      - `name`         - str
      - `description`  - str
      - `focus`        - str  (what this agent looks for, injected into prompt)
      - `agent_tools`  - List[BaseTool]

    And optionally override:
      - `preprocess`   - clean/truncate raw input
      - `postprocess`  - deduplicate/calibrate the result
      - `format_input` - convert the data dict to a prompt string

    The orchestrator calls `agent.run(data)` and receives an AnalysisResult.
    It never needs to know which subclass it is talking to.

    Attributes:
        name (str):           Agent identifier used in logs and results.
        description (str):    Human-readable purpose.
        focus (str):          Domain-specific analysis instructions for the LLM.
        llm:                  LangChain LLM instance.
        agent_executor:       Fully configured ReAct AgentExecutor.
        logger:               Scoped logger for this agent.
    """

    # ------------------------------------------------------------------
    # Abstract declarations — subclasses set these as class attributes
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent identifier (e.g. 'log_agent')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line human-readable purpose of this agent."""

    @property
    @abstractmethod
    def focus(self) -> str:
        """Short paragraph injected into the base prompt.

        Tell the LLM what to look for in this domain — and nothing else.
        Keep it narrow: the agent should not reason about concerns belonging
        to sibling agents (e.g. LogAgent should not mention metrics).
        """

    @property
    @abstractmethod
    def agent_tools(self) -> List[BaseTool]:
        """Domain-specific LangChain tools for this agent.

        These are appended to SHARED_TOOLS when the executor is built.
        Return an empty list if the agent needs no domain tools.
        """

    # ------------------------------------------------------------------
    # Initialisation — wires up the LLM and ReAct executor
    # ------------------------------------------------------------------

    def __init__(
        self,
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        max_iterations: int = 6,
    ):
        """Build the LangChain ReAct executor for this agent.

        Args:
            model_name (str):     OpenAI-compatible model (default gpt-4o).
            temperature (float):  Keep at 0 for reproducible analysis.
            max_iterations (int): ReAct loop iteration cap.
        """
        self.logger = setup_logger(f"kubemind.{self.name}")

        # LLM shared across all tool calls in this agent
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)

        # Merge shared + domain tools
        all_tools = SHARED_TOOLS + self.agent_tools

        # Inject the agent's `focus` into the base prompt
        prompt = PromptTemplate.from_template(
            _BASE_PROMPT_TEMPLATE.replace("{focus}", self.focus)
        )

        # Build the ReAct agent and wrap it in an executor
        react_agent = create_react_agent(
            llm=self.llm,
            tools=all_tools,
            prompt=prompt,
        )
        self.agent_executor = AgentExecutor(
            agent=react_agent,
            tools=all_tools,
            verbose=True,
            max_iterations=max_iterations,
            # Return gracefully instead of raising on malformed LLM output
            handle_parsing_errors=True,
        )

        self.logger.info(
            "Agent '%s' ready — %d tools (%d shared + %d domain-specific)",
            self.name,
            len(all_tools),
            len(SHARED_TOOLS),
            len(self.agent_tools),
        )

    # ------------------------------------------------------------------
    # Public entry point — called by the orchestrator
    # ------------------------------------------------------------------

    async def run(self, data: Dict[str, Any]) -> AnalysisResult:
        """Full lifecycle: preprocess → LLM call → postprocess.

        This is the only method the orchestrator needs to call.
        Children do not override this — they customise the hooks below.

        Args:
            data (Dict[str, Any]): Raw domain input (logs, metrics, events …).

        Returns:
            AnalysisResult: Structured findings ready for the correlator.

        Raises:
            Exception: Re-raises after logging so the orchestrator can decide
                       whether to continue with partial results.
        """
        self.logger.info("Agent '%s' starting analysis", self.name)
        try:
            clean_data   = await self.preprocess(data)
            prompt_input = self.format_input(clean_data)
            result       = await self._call_model(prompt_input, metadata=clean_data)
            final_result = await self.postprocess(result)

            self.logger.info(
                "Agent '%s' done — severity=%s findings=%d confidence=%.2f",
                self.name, final_result.severity,
                len(final_result.findings), final_result.confidence,
            )
            return final_result

        except Exception as exc:
            self.logger.error("Agent '%s' failed: %s", self.name, exc, exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Hooks — subclasses override only what they need
    # ------------------------------------------------------------------

    async def preprocess(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw input before it reaches the LLM.

        Default: pass-through. Override to truncate large payloads,
        strip binary content, convert types, etc.

        Args:
            data (Dict[str, Any]): Raw input from the caller.

        Returns:
            Dict[str, Any]: Cleaned input ready for format_input().
        """
        return data

    async def postprocess(self, result: AnalysisResult) -> AnalysisResult:
        """Enrich or filter the result after the LLM responds.

        Default: pass-through. Override to deduplicate findings,
        clamp confidence, add extra metadata, etc.

        Args:
            result (AnalysisResult): Direct output of _call_model().

        Returns:
            AnalysisResult: Final result forwarded to the orchestrator.
        """
        return result

    def format_input(self, data: Dict[str, Any]) -> str:
        """Serialize the cleaned data dict into the LLM prompt string.

        Default: pretty-printed JSON. Override when a different
        representation is clearer (e.g. raw log text for LogAgent).

        Args:
            data (Dict[str, Any]): Output of preprocess().

        Returns:
            str: The string that will be sent to the ReAct agent as input.
        """
        return json.dumps(data, indent=2, default=str)

    # ------------------------------------------------------------------
    # Core model logic — NOT overridden by children
    # ------------------------------------------------------------------

    async def _call_model(
        self,
        prompt_input: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Invoke the ReAct executor and parse the JSON response.

        This method is private and final — children never call or override it.
        All model interaction is encapsulated here.

        Args:
            prompt_input (str):              Serialized input for the LLM.
            metadata (Dict[str, Any]):       Extra context stored in the result.

        Returns:
            AnalysisResult: Parsed findings, severity, and confidence.
        """
        self.logger.debug("Agent '%s' invoking LLM executor", self.name)

        response = await self.agent_executor.ainvoke({"input": prompt_input})
        raw_output: str = response.get("output", "")

        return self._parse_response(raw_output, metadata=metadata or {})

    def _parse_response(
        self,
        raw_output: str,
        metadata: Dict[str, Any],
    ) -> AnalysisResult:
        """Parse the LLM's Final Answer into an AnalysisResult.

        Strips markdown code fences (the LLM sometimes adds them despite
        instructions) and falls back to a low-confidence INFO result if
        the JSON is malformed — so one bad response never crashes the pipeline.

        Args:
            raw_output (str):       Raw text from the ReAct agent's Final Answer.
            metadata (Dict):        Passed through to AnalysisResult.metadata.

        Returns:
            AnalysisResult: Populated result.
        """
        try:
            # Strip ```json … ``` fences the LLM may add despite instructions
            cleaned = re.sub(r"```(?:json)?|```", "", raw_output).strip()
            parsed  = json.loads(cleaned)

            severity_raw = parsed.get("severity", "info").lower()
            severity = (
                SeverityLevel(severity_raw)
                if severity_raw in SeverityLevel._value2member_map_
                else SeverityLevel.INFO
            )

            return self._build_result(
                findings   = parsed.get("findings", []),
                severity   = severity,
                confidence = float(parsed.get("confidence", 0.5)),
                metadata   = {**metadata, "summary": parsed.get("summary", "")},
            )

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            # Graceful degradation — log the issue but never propagate a parse crash
            self.logger.warning(
                "Agent '%s' could not parse LLM response as JSON: %s", self.name, exc
            )
            return self._build_result(
                findings   = [raw_output] if raw_output else ["Analysis produced no output."],
                severity   = SeverityLevel.LOW,
                confidence = 0.2,
                metadata   = {**metadata, "parse_error": str(exc)},
            )

    def _build_result(
        self,
        findings:   List[str],
        severity:   SeverityLevel           = SeverityLevel.INFO,
        confidence: float                   = 0.5,
        raw_data:   Optional[Any]           = None,
        metadata:   Optional[Dict[str, Any]]= None,
    ) -> AnalysisResult:
        """Construct a standardized AnalysisResult.

        Single place where AnalysisResult is instantiated — keeps the
        agent_name and timestamp consistent across all agents.

        Args:
            findings (List[str]):     Discovered issues or observations.
            severity (SeverityLevel): Highest severity found.
            confidence (float):       LLM confidence score in [0, 1].
            raw_data:                 Optional raw payload to forward downstream.
            metadata (dict):          Extra key-value context.

        Returns:
            AnalysisResult: Ready for the orchestrator.
        """
        return AnalysisResult(
            agent_name = self.name,
            findings   = findings,
            severity   = severity,
            confidence = confidence,
            timestamp  = datetime.now(timezone.utc),
            raw_data   = raw_data,
            metadata   = metadata or {},
        )