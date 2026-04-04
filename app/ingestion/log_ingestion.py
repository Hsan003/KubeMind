import re
from datetime import datetime
from app.models.log_models import PodLog, EnrichedLog, LogSeverity
from app.ingestion.k8s_client import K8sClient
from app.storage.loki_client import LokiClient

# --- Pattern Registry ---
ERROR_PATTERNS = {
    r"OOMKilled|out of memory":        "oom_kill",
    r"CrashLoopBackOff":               "crash_loop",
    r"ImagePullBackOff|ErrImagePull":  "image_pull_failure",
    r"connection refused":             "connection_refused",
    r"timeout|timed out":              "timeout",
    r"permission denied":              "permission_denied",
    r"FATAL|panic:":                   "fatal_error",
    r"Readiness probe failed":         "readiness_probe_failed",
    r"Liveness probe failed":          "liveness_probe_failed",
}

SEVERITY_KEYWORDS = {
    LogSeverity.CRITICAL: ["fatal", "panic", "oomkilled", "crashloopbackoff"],
    LogSeverity.ERROR:    ["error", "exception", "failed", "failure"],
    LogSeverity.WARNING:  ["warn", "warning", "deprecated", "timeout"],
    LogSeverity.DEBUG:    ["debug", "trace"],
}

# --- Helpers ---
def classify_severity(message: str) -> LogSeverity:
    lower = message.lower()
    for severity, keywords in SEVERITY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return severity
    return LogSeverity.INFO

def detect_patterns(message: str) -> list[str]:
    return [
        label for pattern, label in ERROR_PATTERNS.items()
        if re.search(pattern, message, re.IGNORECASE)
    ]

def parse_timestamp(line: str) -> tuple[datetime, str]:
    """Extract leading RFC3339 timestamp from a log line."""
    parts = line.split(" ", 1)
    try:
        ts = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        message = parts[1] if len(parts) > 1 else line
    except (ValueError, IndexError):
        ts = datetime.utcnow()
        message = line
    return ts, message


# --- Main Service ---
class LogIngestionService:
    def __init__(self, k8s_client: K8sClient, loki_client: LokiClient, cluster_name: str):
        self.k8s = k8s_client
        self.loki = loki_client
        self.cluster_name = cluster_name

    async def ingest_namespace(self, namespace: str) -> list[EnrichedLog]:
        enriched_logs = []
        pods = self.k8s.list_pods(namespace)

        for pod in pods:
            for container in pod.spec.containers:
                raw_logs = self.k8s.fetch_pod_logs(
                    pod_name=pod.metadata.name,
                    namespace=namespace,
                    container=container.name,
                )
                for line in raw_logs.splitlines():
                    if not line.strip():
                        continue

                    ts, message = parse_timestamp(line)

                    pod_log = PodLog(
                        pod_name=pod.metadata.name,
                        namespace=namespace,
                        container=container.name,
                        timestamp=ts,
                        raw_message=message,
                        severity=classify_severity(message),
                        labels=dict(pod.metadata.labels or {}),
                    )

                    enriched = EnrichedLog(
                        **pod_log.model_dump(),
                        cluster_name=self.cluster_name,
                        error_patterns=detect_patterns(message),
                    )

                    await self.loki.push(enriched)
                    enriched_logs.append(enriched)

        return enriched_logs