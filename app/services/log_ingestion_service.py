import logging
from dataclasses import dataclass, field

from app.ingestion.log_collector import LogCollector
from app.models.log_models import LogEntry, LogQueryParams
from app.storage.loki_storage import LokiStorage

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary returned after a collection + push run."""

    namespace: str
    total_entries: int = 0
    pushed_to_loki: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.pushed_to_loki and not self.errors


class LogIngestionService:
    """
    Orchestrates the log collection pipeline:

      K8s pods  →  LogCollector  →  [optional transform]  →  LokiStorage

    Instantiate once per request (or share as a singleton — it is stateless).
    """

    def __init__(self, loki_url: str) -> None:
        self._collector = LogCollector()
        self._loki = LokiStorage(url=loki_url)

    # ------------------------------------------------------------------
    # High-level entry points
    # ------------------------------------------------------------------

    async def ingest_namespace(self, namespace: str, **kwargs) -> IngestionResult:
        """
        Convenience method: collect *all* pods in a namespace and push to Loki.

        Extra kwargs are forwarded to LogQueryParams (since_seconds, tail_lines, etc.)
        """
        params = LogQueryParams(namespace=namespace, **kwargs)
        return await self.ingest(params)

    async def ingest(self, params: LogQueryParams) -> IngestionResult:
        """
        Full pipeline:
        1. Collect log entries from Kubernetes.
        2. Apply lightweight transforms (e.g. filter noise).
        3. Push to Loki in one batched call.
        """
        result = IngestionResult(namespace=params.namespace)

        # 1. Collect
        try:
            entries: list[LogEntry] = self._collector.collect(params)
            result.total_entries = len(entries)
        except Exception as exc:
            msg = f"Log collection failed: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
            return result

        if not entries:
            logger.info("No log entries found for namespace=%s", params.namespace)
            return result

        # 2. Optional transform — filter empty messages, deduplicate, etc.
        entries = self._filter_entries(entries)

        # 3. Push to Loki
        try:
            ok = await self._loki.push(entries)
            result.pushed_to_loki = ok
            if not ok:
                result.errors.append("Loki push returned a non-200 status.")
        except Exception as exc:
            msg = f"Loki push raised an exception: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        logger.info(
            "Ingestion complete: namespace=%s entries=%d success=%s",
            result.namespace, result.total_entries, result.success,
        )
        return result

    async def ingest_many(self, namespaces: list[str], **kwargs) -> list[IngestionResult]:
        """Run ingestion for multiple namespaces sequentially."""
        results = []
        for ns in namespaces:
            results.append(await self.ingest_namespace(ns, **kwargs))
        return results

    async def health(self) -> dict:
        """Return liveness info — call from a FastAPI health endpoint."""
        loki_ok = await self._loki.health_check()
        return {"loki": "ok" if loki_ok else "unreachable"}

    # ------------------------------------------------------------------
    # Transform helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_entries(entries: list[LogEntry]) -> list[LogEntry]:
        """
        Drop entries that carry no useful signal.
        Extend this as needed (e.g. remove known-noisy pod prefixes).
        """
        return [e for e in entries if e.message.strip()]