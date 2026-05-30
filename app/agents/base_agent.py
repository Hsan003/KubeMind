"""Base abstraction for Kubernetes-oriented LangChain agents."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
loki_service: LokiSer
from config.settings import get_settings


class BaseK8sAgent(ABC):
    """Reusable base class for all KubeMind LangChain agents.

    Responsibilities:
    - initialize LLM runtime
    - build system prompt and toolset
    - configure LangChain v1 create_agent runtime
    - provide a single async run entrypoint
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        llm: Optional[Any] = None,
        max_iterations: Optional[int] = None,
        verbose: Optional[bool] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.settings = get_settings()
        self.llm = llm or self._init_llm()
        self.max_iterations = max_iterations or self.settings.AGENT_MAX_ITERATIONS
        self.verbose = self.settings.AGENT_VERBOSE if verbose is None else verbose
        self.tools = self._build_tools()
        self.executor = self._build_executor()

    def _init_llm(self) -> Any:
        """Initialize the configured provider model for agents."""
        provider = str(self.settings.MODEL_PROVIDER).strip().lower()
        if provider == "google":
            kwargs: Dict[str, Any] = {
                "model": self.settings.MODEL_NAME,
                "temperature": self.settings.AGENT_TEMPERATURE,
            }
            api_key = self.settings.GOOGLE_API_KEY or self.settings.MODEL_API_KEY
            if api_key:
                kwargs["google_api_key"] = api_key
            return ChatGoogleGenerativeAI(**kwargs)

        kwargs = {
            "model": self.settings.OPENAI_MODEL,
            "temperature": self.settings.AGENT_TEMPERATURE,
        }
        api_key = self.settings.OPENAI_API_KEY or self.settings.MODEL_API_KEY
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)

    @abstractmethod
    def _build_tools(self) -> List[BaseTool]:
        """Return LangChain tools exposed to this agent."""

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Return system role and operating instructions for this agent."""

    def _build_executor(self) -> Any:
        """Create LangChain v1 agent runtime with tool-calling support."""
        return create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self._build_system_prompt(),
        )

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute the agent with optional context and return structured output."""
        context = context or {}
        composed_input = self._compose_input(user_input=user_input, context=context)
        result = await self.executor.ainvoke(
            {"messages": [{"role": "user", "content": composed_input}]}
        )
        messages = result.get("messages", []) if isinstance(result, dict) else []
        return {
            "agent_name": self.name,
            "input": user_input,
            "context": context,
            "output": self._extract_output(messages=messages),
            "intermediate_steps": self._extract_intermediate_steps(messages=messages),
        }

    def _compose_input(self, user_input: str, context: Dict[str, Any]) -> str:
        """Combine user input and context into one deterministic prompt payload."""
        if not context:
            return user_input
        serialized_context = json.dumps(context, default=str, ensure_ascii=True, sort_keys=True)
        return f"{user_input}\n\nContext:\n{serialized_context}"

    def _extract_output(self, messages: List[Any]) -> str:
        """Extract final assistant text from agent message history."""
        for message in reversed(messages):
            msg_type = getattr(message, "type", None)
            if msg_type not in ("ai", "assistant"):
                continue
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts: List[str] = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(str(text))
                if text_parts:
                    return "\n".join(text_parts).strip()
        return ""

    def _extract_intermediate_steps(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Capture tool call and tool result messages for debugging."""
        steps: List[Dict[str, Any]] = []
        for message in messages:
            msg_type = getattr(message, "type", None)
            if msg_type == "ai":
                tool_calls = getattr(message, "tool_calls", None) or []
                for call in tool_calls:
                    if isinstance(call, dict):
                        steps.append(
                            {
                                "type": "tool_call",
                                "name": call.get("name"),
                                "args": call.get("args"),
                            }
                        )
            elif msg_type == "tool":
                steps.append(
                    {
                        "type": "tool_result",
                        "name": getattr(message, "name", None),
                        "content": getattr(message, "content", ""),
                    }
                )
        return steps
