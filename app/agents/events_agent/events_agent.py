"""Kubernetes events analysis agent.

Configuration-only child of BaseAgent. Declares its focus (K8s API events),
its tools (warning filter, backoff/image-pull detection, frequency counter),
and preprocessing that normalises Pydantic models to plain dicts and caps
the event list size. All model interaction stays in BaseAgent.

Usage:
    result = await EventsAgent().run({
        "events": [
            {"type": "Warning", "reason": "BackOff",
             "message": "Back-off restarting failed container",
             "namespace": "prod", "object_kind": "Pod", "object_name": "api-xyz",
             "timestamp": "2026-05-26T10:00:00Z"},
        ],
        "namespace": "prod",
    })
"""

import json
import re
from collections import Counter
from typing import Any, Dict, List

from langchain.tools import BaseTool, tool

from app.agents.base_agent import BaseAgent
from app.models.analysis import AnalysisResult


# ---------------------------------------------------------------------------
# Events-specific tools
# ---------------------------------------------------------------------------

@tool
def filter_warning_events(events_json: str) -> str:
    """Return only Warning-type events from a JSON array.

    Args:
        events_json: JSON array of Kubernetes event objects (each with a 'type' field).

    Returns:
        JSON array of Warning events, or 'No Warning events found.'
    """
    try:
        events = json.loads(events_json)
    except json.JSONDecodeError:
        return "Could not parse events JSON."

    warnings = [e for e in events if str(e.get("type", "")).lower() == "warning"]
    return json.dumps(warnings, default=str) if warnings else "No Warning events found."


@tool
def detect_backoff_events(events_json: str) -> str:
    """Identify BackOff or CrashLoopBackOff events in the stream.

    Args:
        events_json: JSON array of Kubernetes event objects.

    Returns:
        Affected object names and messages, or 'No backoff events found.'
    """
    try:
        events = json.loads(events_json)
    except json.JSONDecodeError:
        return "Could not parse events JSON."

    pattern = re.compile(r"back.?off|crashloop", re.IGNORECASE)
    hits = [
        f"{e.get('object_kind','?')}/{e.get('object_name','?')}: {e.get('message','')}"
        for e in events
        if pattern.search(e.get("reason", "") + e.get("message", ""))
    ]
    return "\n".join(hits) if hits else "No backoff events found."


@tool
def detect_image_pull_errors(events_json: str) -> str:
    """Find image pull failures (ErrImagePull, ImagePullBackOff) in the event stream.

    Args:
        events_json: JSON array of Kubernetes event objects.

    Returns:
        Affected pods and error messages, or 'No image pull errors found.'
    """
    try:
        events = json.loads(events_json)
    except json.JSONDecodeError:
        return "Could not parse events JSON."

    pattern = re.compile(r"errimagepull|imagepullbackoff|failed to pull", re.IGNORECASE)
    hits = [
        f"{e.get('object_name','?')}: {e.get('message','')}"
        for e in events
        if pattern.search(e.get("reason", "") + e.get("message", ""))
    ]
    return "\n".join(hits) if hits else "No image pull errors found."


@tool
def count_events_by_reason(events_json: str) -> str:
    """Count events grouped by their 'reason' field, sorted by frequency.

    Useful for spotting high-frequency failure patterns like repeated
    'BackOff' or 'Killing' events in a short observation window.

    Args:
        events_json: JSON array of Kubernetes event objects.

    Returns:
        JSON object mapping reason → count, descending.
    """
    try:
        events = json.loads(events_json)
    except json.JSONDecodeError:
        return "Could not parse events JSON."

    counts = dict(
        sorted(Counter(e.get("reason", "Unknown") for e in events).items(), key=lambda x: -x[1])
    )
    return json.dumps(counts)


# ---------------------------------------------------------------------------
# EventsAgent
# ---------------------------------------------------------------------------

class EventsAgent(BaseAgent):
    """Analyzes Kubernetes API events for cluster health issues.

    Configuration-only child — never calls the LLM directly.
    """

    # Cap the event list to avoid overflowing the context window
    _MAX_EVENTS = 200

    # ------------------------------------------------------------------
    # Agent configuration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "events_agent"

    @property
    def description(self) -> str:
        return "Analyzes Kubernetes API events for cluster health issues"

    @property
    def focus(self) -> str:
        """Scoped to Kubernetes API events only."""
        return (
            "You are analyzing a stream of Kubernetes API events. "
            "Look for: CrashLoopBackOff (repeated BackOff events on the same pod), "
            "image pull failures (ErrImagePull, ImagePullBackOff — wrong tag or missing secret), "
            "OOMKilled events (memory limit too low), "
            "FailedScheduling (node resource exhaustion or taint/toleration mismatch), "
            "Evicted pods (node under memory/disk pressure), "
            "FailedMount / FailedAttach (PVC or volume issues). "
            "A single Warning is usually noise; repeated Warnings on the same object "
            "within a short window indicate an active incident."
        )

    @property
    def agent_tools(self) -> List[BaseTool]:
        return [filter_warning_events, detect_backoff_events, detect_image_pull_errors, count_events_by_reason]

    # ------------------------------------------------------------------
    # Optional hooks
    # ------------------------------------------------------------------

    async def preprocess(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise events to plain dicts and enforce the size cap.

        Converts Pydantic model instances to dicts (supports both v1 .dict()
        and v2 .model_dump()), removes None values, and keeps only the most
        recent _MAX_EVENTS entries.

        Args:
            data: Must contain 'events' (List[dict | Pydantic model]).

        Returns:
            Cleaned data with 'events' as a list of plain dicts.
        """
        raw: list = data.get("events", [])
        normalized: List[Dict] = []

        for e in raw:
            # Accept Pydantic v1 and v2 model instances
            if hasattr(e, "model_dump"):
                e = e.model_dump()
            elif hasattr(e, "dict"):
                e = e.dict()
            # Drop None values to reduce token count
            normalized.append({k: v for k, v in e.items() if v is not None})

        if len(normalized) > self._MAX_EVENTS:
            self.logger.warning(
                "Event list truncated from %d to %d entries", len(normalized), self._MAX_EVENTS
            )
            normalized = normalized[-self._MAX_EVENTS:]   # Keep most recent

        return {**data, "events": normalized}

    def format_input(self, data: Dict[str, Any]) -> str:
        """Serialize the event list with namespace context.

        Args:
            data: Cleaned data from preprocess().

        Returns:
            Prompt string with namespace + JSON event array.
        """
        namespace = data.get("namespace", "all")
        events    = data.get("events", [])

        return (
            f"Namespace: {namespace} | Event count: {len(events)}\n\n"
            f"--- EVENTS (JSON) ---\n"
            f"{json.dumps(events, indent=2, default=str)}\n"
            f"--- END ---"
        )