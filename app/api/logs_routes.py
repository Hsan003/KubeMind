from fastapi import APIRouter, HTTPException, Query
# ------------------------------------------------------------------
# Endpoints
from pydantic import BaseModel

from app.models.log_models import LogQueryParams
from app.services.log_ingestion_service import IngestionResult, LogIngestionService
from config.settings import get_settings

router = APIRouter(prefix="/ingest", tags=["log-ingestion"])

# from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.storage.loki_storage import LokiStorage
from app.services.loki_service import LokiService
from app.agents.log_agent.logs_agent import LogsAgent


class LogsAgentRequest(BaseModel):
    query: str = Field(
        description="Natural language question about logs.",
        examples=["Show me all ERROR logs from payments in the last 30 minutes"],
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional structured metadata forwarded to the agent (namespace, cluster, etc.).",
        examples=[{"namespace": "prod", "cluster": "us-east-1"}],
    )


class IntermediateStep(BaseModel):
    type: str  # "tool_call" | "tool_result"
    name: Optional[str] = None
    args: Optional[Dict[str, Any]] = None  # present on tool_call
    content: Optional[str] = None  # present on tool_result


class LogsAgentResponse(BaseModel):
    agent_name: str
    query: str
    context: Dict[str, Any]
    output: str
    intermediate_steps: List[IntermediateStep]
    duration_ms: float


class HealthResponse(BaseModel):
    status: str
    loki_reachable: bool


# ─────────────────────────────────────────────
# Dependency — build agent once per request
# (swap for a singleton / lifespan pattern in prod)
# ─────────────────────────────────────────────

def get_loki_service() -> LokiService:
    """Create LokiService from settings. Override in tests via app.dependency_overrides."""
    from config.settings import get_settings
    settings = get_settings()
    storage = LokiStorage(url=settings.loki_url)
    return LokiService(storage=storage)


def get_logs_agent(service: LokiService = Depends(get_loki_service)) -> LogsAgent:
    return LogsAgent(loki_service=service)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post(
    "/run",
    response_model=LogsAgentResponse,
    summary="Run the logs agent",
    description=(
            "Send a natural language query to the LogsAgent. "
            "The agent constructs a LogQL query, fetches logs from Loki, "
            "and returns a human-readable analysis together with the raw "
            "intermediate tool calls for debugging."
    ),
)
async def run_logs_agent(
        body: LogsAgentRequest,
        agent: LogsAgent = Depends(get_logs_agent),
) -> LogsAgentResponse:
    start = time.monotonic()

    try:
        result = await agent.run(
            user_input=body.query,
            context=body.context or {},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent execution failed: {exc}",
        ) from exc

    duration_ms = (time.monotonic() - start) * 1000

    steps = [
        IntermediateStep(
            type=s["type"],
            name=s.get("name"),
            args=s.get("args"),
            content=s.get("content"),
        )
        for s in result.get("intermediate_steps", [])
    ]

    return LogsAgentResponse(
        agent_name=result["agent_name"],
        query=result["input"],
        context=result["context"],
        output=result["output"],
        intermediate_steps=steps,
        duration_ms=round(duration_ms, 2),
    )

def _get_service() -> LogIngestionService:
    """Lightweight factory — creates a service with settings from env."""
    settings = get_settings()
    return LogIngestionService(loki_url=settings.loki_url)


# ------------------------------------------------------------------
# Request / response schemas
# ------------------------------------------------------------------

class IngestRequest(BaseModel):
    namespace: str = "demo"
    pod_name: str | None = None
    container_name: str | None = None
    since_seconds: int = 3600
    tail_lines: int = 500
    include_previous: bool = False


class IngestResponse(BaseModel):
    namespace: str
    total_entries: int
    pushed_to_loki: bool
    success: bool
    errors: list[str]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/logs", response_model=IngestResponse, summary="Collect and store pod logs")
async def ingest_logs(body: IngestRequest) -> IngestResponse:
    """
    Trigger log collection for the given namespace (optionally scoped to a pod/container)
    and push results to Loki.
    """
    service = _get_service()
    params = LogQueryParams(**body.model_dump())
    result: IngestionResult = await service.ingest(params)

    if result.errors and not result.pushed_to_loki:
        raise HTTPException(status_code=502, detail=result.errors)

    return IngestResponse(
        namespace=result.namespace,
        total_entries=result.total_entries,
        pushed_to_loki=result.pushed_to_loki,
        success=result.success,
        errors=result.errors,
    )


@router.post(
    "/logs/namespaces",
    response_model=list[IngestResponse],
    summary="Ingest logs from multiple namespaces",
)
async def ingest_many_namespaces(
    namespaces: list[str],
    since_seconds: int = Query(default=3600, ge=60, le=86400),
    tail_lines: int = Query(default=500, ge=10, le=5000),
) -> list[IngestResponse]:
    """
    Batch endpoint: ingest logs from a list of namespaces in one call.
    """
    service = _get_service()
    results = await service.ingest_many(
        namespaces, since_seconds=since_seconds, tail_lines=tail_lines
    )
    return [
        IngestResponse(
            namespace=r.namespace,
            total_entries=r.total_entries,
            pushed_to_loki=r.pushed_to_loki,
            success=r.success,
            errors=r.errors,
        )
        for r in results
    ]


@router.get("/health", summary="Check ingestion service health")
async def ingestion_health() -> dict:
    service = _get_service()
    return await service.health()