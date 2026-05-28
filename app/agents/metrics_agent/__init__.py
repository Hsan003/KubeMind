"""Metrics agent implementation built on LangChain ReAct."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool

from app.agents.base_agent import BaseK8sAgent
from app.agents.metrics_agent.prompts import build_metrics_system_prompt
from app.agents.metrics_agent.tools import build_collect_metrics_tool
from app.services.incident_orchestrator import IncidentOrchestrator


class MetricsAgent(BaseK8sAgent):
    """Agent responsible for Kubernetes metrics collection and interpretation."""

    def __init__(
        self,
        orchestrator: Optional[IncidentOrchestrator] = None,
        llm: Optional[Any] = None,
        max_iterations: Optional[int] = None,
        verbose: Optional[bool] = None,
    ) -> None:
        self.orchestrator = orchestrator or IncidentOrchestrator()
        super().__init__(
            name="metrics_agent",
            description="Collects and interprets Kubernetes workload metrics",
            llm=llm,
            max_iterations=max_iterations,
            verbose=verbose,
        )

    def _build_tools(self) -> list[BaseTool]:
        """Expose metric collection capability to the ReAct runtime."""
        return [build_collect_metrics_tool(orchestrator=self.orchestrator)]

    def _build_system_prompt(self) -> str:
        """Return active-role system prompt for metrics investigations."""
        return build_metrics_system_prompt()

    async def analyze_metrics(
        self,
        question: str,
        scope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze metrics using ReAct and Prometheus-backed collection tool."""
        return await self.run(user_input=question, context=scope or {})


__all__ = ["MetricsAgent"]
