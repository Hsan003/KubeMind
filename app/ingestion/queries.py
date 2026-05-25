"""PromQL query catalog for metrics collection."""

import re
from typing import Dict, List

from app.models.metrics import MetricsCollectionRequest

CPU_USAGE = "cpu_usage"
MEMORY_USAGE = "memory_usage"
RESTART_COUNT = "restart_count"
REQUEST_RATE = "request_rate"
ERROR_RATE = "error_rate"

GOLDEN_SIGNAL_KEYS: List[str] = [
    CPU_USAGE,
    MEMORY_USAGE,
    RESTART_COUNT,
    REQUEST_RATE,
    ERROR_RATE,
]

PROMETHEUS_HEALTH_QUERY = "up"


def _build_base_matchers(request: MetricsCollectionRequest) -> str:
    """Build common label matchers from the incoming request."""
    matchers = [f'namespace="{request.namespace}"']

    if request.pod_name:
        matchers.append(f'pod="{request.pod_name}"')
    elif request.workload_name:
        workload_name = re.escape(request.workload_name)
        matchers.append(f'pod=~"^{workload_name}.*"')
    if request.container_name:
        matchers.append(f'container="{request.container_name}"')

    return ",".join(matchers)


def _compose_matchers(base_matchers: str, extra_matchers: List[str]) -> str:
    """Merge common matchers with metric-specific matchers."""
    all_matchers = [base_matchers]
    all_matchers.extend(extra_matchers)
    return ",".join([matcher for matcher in all_matchers if matcher])


def build_range_queries(request: MetricsCollectionRequest) -> Dict[str, str]:
    """Build range queries for V1 golden signals."""
    base_matchers = _build_base_matchers(request)
    pod_filters = ['container!="POD"']

    cpu_matchers = _compose_matchers(base_matchers, pod_filters)
    memory_matchers = _compose_matchers(base_matchers, pod_filters)
    cpu_matchers_with_image = _compose_matchers(base_matchers, pod_filters + ['image!=""'])
    memory_matchers_with_image = _compose_matchers(base_matchers, pod_filters + ['image!=""'])
    restarts_matchers = base_matchers
    requests_matchers = base_matchers
    errors_matchers = _compose_matchers(base_matchers, ['status=~"5.."'])

    cpu_usage_expr = (
        f"(sum(rate(container_cpu_usage_seconds_total{{{cpu_matchers_with_image}}}[5m])) "
        "by (namespace,pod,container)) "
        f"or (sum(rate(container_cpu_usage_seconds_total{{{cpu_matchers}}}[5m])) "
        "by (namespace,pod,container))"
    )
    memory_usage_expr = (
        f"(sum(container_memory_working_set_bytes{{{memory_matchers_with_image}}}) "
        "by (namespace,pod,container)) "
        f"or (sum(container_memory_working_set_bytes{{{memory_matchers}}}) "
        "by (namespace,pod,container))"
    )

    # Support both common app metrics:
    # - http_requests_total (service metrics with status label)
    # - demo_requests_total / demo_errors_total (demo generator app)
    request_rate_http = (
        f"sum(rate(http_requests_total{{{requests_matchers}}}[5m])) by (namespace,pod)"
    )
    request_rate_demo = (
        f"sum(rate(demo_requests_total{{{requests_matchers}}}[5m])) by (namespace,pod)"
    )
    request_rate_expr = f"(({request_rate_http}) or ({request_rate_demo}))"

    error_rate_http = (
        f"sum(rate(http_requests_total{{{errors_matchers}}}[5m])) by (namespace,pod)"
    )
    error_rate_demo = (
        f"sum(rate(demo_errors_total{{{requests_matchers}}}[5m])) by (namespace,pod)"
    )
    error_rate_expr = (
        f"(({error_rate_http}) or ({error_rate_demo})) / "
        f"clamp_min({request_rate_expr}, 1)"
    )

    return {
        CPU_USAGE: cpu_usage_expr,
        MEMORY_USAGE: memory_usage_expr,
        RESTART_COUNT: (
            f"sum(kube_pod_container_status_restarts_total{{{restarts_matchers}}}) "
            "by (namespace,pod,container)"
        ),
        REQUEST_RATE: request_rate_expr,
        ERROR_RATE: error_rate_expr,
    }


def build_instant_queries(request: MetricsCollectionRequest) -> Dict[str, str]:
    """Build instant queries for current-state snapshots."""
    base_matchers = _build_base_matchers(request)
    return {
        RESTART_COUNT: (
            f"sum(kube_pod_container_status_restarts_total{{{base_matchers}}}) "
            "by (namespace,pod,container)"
        ),
        PROMETHEUS_HEALTH_QUERY: PROMETHEUS_HEALTH_QUERY,
    }

