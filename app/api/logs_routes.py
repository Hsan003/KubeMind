from fastapi import APIRouter, HTTPException, Query
# ------------------------------------------------------------------
# Endpoints
from pydantic import BaseModel

from app.models.log_models import LogQueryParams
from app.services.log_ingestion_service import IngestionResult, LogIngestionService
from config.settings import get_settings

router = APIRouter(prefix="/ingest", tags=["log-ingestion"])


def _get_service() -> LogIngestionService:
    """Lightweight factory — creates a service with settings from env."""
    settings = get_settings()
    return LogIngestionService(loki_url=settings.loki_url)


# ------------------------------------------------------------------
# Request / response schemas
# ------------------------------------------------------------------

class IngestRequest(BaseModel):
    namespace: str
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