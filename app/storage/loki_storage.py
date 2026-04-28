import logging
from collections import defaultdict

import httpx

from app.models.log_models import LogEntry

logger = logging.getLogger(__name__)

# Loki's push endpoint
_PUSH_PATH = "/loki/api/v1/push"


def _to_ns(ts) -> str:
    """Convert a datetime to a nanosecond-precision Unix timestamp string (Loki format)."""
    epoch_ns = int(ts.timestamp() * 1_000_000_000)
    return str(epoch_ns)


def _build_stream_key(entry: LogEntry) -> tuple[str, ...]:
    """Return a hashable key that groups log entries into the same Loki stream."""
    return (entry.namespace, entry.pod_name, entry.container_name)


def _build_payload(entries: list[LogEntry]) -> dict:
    """
    Group entries by stream labels and build the Loki push payload:

    {
      "streams": [
        {
          "stream": {"namespace": "...", "pod": "...", "container": "...", "level": "..."},
          "values": [["<ts_ns>", "<log line>"], ...]
        },
        ...
      ]
    }
    """
    # Group entries by stream key
    groups: dict[tuple, list[LogEntry]] = defaultdict(list)
    for entry in entries:
        groups[_build_stream_key(entry)].append(entry)

    streams = []
    for (namespace, pod, container), group in groups.items():
        # Determine a single level label for the stream (most common level wins)
        levels = [e.log_level for e in group if e.log_level]
        level_label = max(set(levels), key=levels.count) if levels else "UNKNOWN"

        stream_labels = {
            "namespace": namespace,
            "pod": pod,
            "container": container,
            "level": level_label,
            "job": "k8s-ai-incident-analyzer",
            "source": "kubernetes",
        }

        # Sort values by timestamp (Loki requires chronological order within a stream)
        values = [
            [_to_ns(e.timestamp), e.message]
            for e in sorted(group, key=lambda e: e.timestamp)
        ]

        streams.append({"stream": stream_labels, "values": values})

    return {"streams": streams}


class LokiStorage:
    """
    Async client for pushing log entries to a Grafana Loki instance.

    Usage::

        loki = LokiStorage(url="http://loki:3100")
        await loki.push(entries)
    """

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.base_url = url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def push(self, entries: list[LogEntry]) -> bool:
        """
        Push a batch of LogEntry objects to Loki.
        Returns True on success, False on failure (logs the error internally).
        """
        if not entries:
            logger.debug("LokiStorage.push called with empty list — skipping.")
            return True

        payload = _build_payload(entries)
        return await self._post(payload)

    async def push_stream(self, entries_iter) -> int:
        """
        Consume an async/sync iterable of LogEntry and push in configurable batches.
        Returns total number of entries pushed.
        """
        batch: list[LogEntry] = []
        total = 0
        batch_size = 500

        for entry in entries_iter:
            batch.append(entry)
            if len(batch) >= batch_size:
                await self.push(batch)
                total += len(batch)
                batch = []

        if batch:
            await self.push(batch)
            total += len(batch)

        return total

    async def health_check(self) -> bool:
        """Ping Loki's ready endpoint — useful for startup checks."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/ready")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Loki health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _post(self, payload: dict) -> bool:
        url = f"{self.base_url}{_PUSH_PATH}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 204):
                    logger.debug(
                        "Loki push succeeded: %d streams, status=%d",
                        len(payload["streams"]), resp.status_code,
                    )
                    return True
                logger.error(
                    "Loki push failed: status=%d body=%s", resp.status_code, resp.text[:200]
                )
                return False
        except httpx.TimeoutException:
            logger.error("Loki push timed out (url=%s)", url)
            return False
        except httpx.RequestError as exc:
            logger.error("Loki push connection error: %s", exc)
            return False