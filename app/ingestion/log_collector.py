import re
import logging
from datetime import datetime, timezone
from typing import Generator

from kubernetes.client.exceptions import ApiException

from app.models.log_models import LogEntry, LogQueryParams
from app.services.k8s_service import K8sService

logger = logging.getLogger(__name__)

# Naive level detector — looks for common log-level tokens in a line
_LEVEL_RE = re.compile(
    r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE
)

# RFC3339 / ISO-8601 timestamp at the start of a log line (K8s --timestamps format)
_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+"
)


def _extract_level(line: str) -> str | None:
    m = _LEVEL_RE.search(line)
    return m.group(1).upper() if m else None


def _parse_timestamp(line: str) -> tuple[datetime, str]:
    """
    Try to strip an RFC3339 timestamp prepended by the K8s API (--timestamps).
    Returns (datetime, remainder_of_line).
    Falls back to utcnow if no timestamp is found.
    """
    m = _TS_RE.match(line)
    if m:
        ts_str = m.group(1)
        remainder = line[m.end():]
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return ts, remainder
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc), line


class LogCollector:
    """
    Fetches raw logs from Kubernetes pods and yields structured LogEntry objects.

    Uses the shared K8sService singleton so no extra API client is created.
    """

    def __init__(self) -> None:
        self._k8s = K8sService.get_instance()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self, params: LogQueryParams) -> list[LogEntry]:
        """
        Collect logs for all matching pods and return them as a flat list.
        Pods are discovered first, then logs are fetched per-container.
        """
        entries: list[LogEntry] = []
        pods = self._list_pods(params)

        for pod in pods:
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            pod_labels = pod.metadata.labels or {}

            containers = [c.name for c in (pod.spec.containers or [])]
            if params.container_name:
                containers = [c for c in containers if c == params.container_name]

            for container in containers:
                try:
                    raw = self._fetch_raw_logs(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container,
                        since_seconds=params.since_seconds,
                        tail_lines=params.tail_lines,
                        previous=params.include_previous,
                    )
                    entries.extend(
                        self._parse_log_lines(
                            raw=raw,
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container,
                            pod_labels=pod_labels,
                        )
                    )
                except ApiException as exc:
                    logger.warning(
                        "Failed to fetch logs for %s/%s[%s]: %s",
                        namespace, pod_name, container, exc.reason,
                    )
                    continue

        logger.info(
            "Collected %d log entries from namespace=%s", len(entries), params.namespace
        )
        return entries

    def stream(self, params: LogQueryParams) -> Generator[LogEntry, None, None]:
        """
        Generator variant — yields entries one by one (memory-efficient for large clusters).
        """
        pods = self._list_pods(params)
        for pod in pods:
            pod_name = pod.metadata.name
            namespace = pod.metadata.namespace
            pod_labels = pod.metadata.labels or {}
            containers = [c.name for c in (pod.spec.containers or [])]
            if params.container_name:
                containers = [c for c in containers if c == params.container_name]

            for container in containers:
                try:
                    raw = self._fetch_raw_logs(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container,
                        since_seconds=params.since_seconds,
                        tail_lines=params.tail_lines,
                        previous=params.include_previous,
                    )
                    yield from self._parse_log_lines(
                        raw=raw,
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container,
                        pod_labels=pod_labels,
                    )
                except ApiException as exc:
                    logger.warning(
                        "Skipping %s/%s[%s]: %s", namespace, pod_name, container, exc.reason
                    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _list_pods(self, params: LogQueryParams):
        """Return a list of pod objects matching the query params."""
        try:
            if params.pod_name:
                pod = self._k8s.core_v1.read_namespaced_pod(
                    name=params.pod_name, namespace=params.namespace
                )
                return [pod]
            resp = self._k8s.core_v1.list_namespaced_pod(namespace=params.namespace)
            return resp.items
        except ApiException as exc:
            logger.error("Failed to list pods in %s: %s", params.namespace, exc.reason)
            return []

    def _fetch_raw_logs(
        self,
        *,
        namespace: str,
        pod_name: str,
        container_name: str,
        since_seconds: int,
        tail_lines: int,
        previous: bool,
    ) -> str:
        """
        Call the Kubernetes API to get pod logs as a raw string.
        timestamps=True prepends an RFC3339 timestamp to every line.
        """
        return self._k8s.core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container_name,
            since_seconds=since_seconds,
            tail_lines=tail_lines,
            previous=previous,
            timestamps=True,   # lets us parse per-line timestamps
        )

    def _parse_log_lines(
        self,
        *,
        raw: str,
        namespace: str,
        pod_name: str,
        container_name: str,
        pod_labels: dict[str, str],
    ) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            ts, message = _parse_timestamp(line)
            entries.append(
                LogEntry(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    timestamp=ts,
                    message=message,
                    labels=pod_labels,
                    log_level=_extract_level(message),
                )
            )
        return entries