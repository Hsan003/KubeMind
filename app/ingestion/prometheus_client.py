"""Async client for Prometheus HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

import httpx

from app.ingestion.queries import PROMETHEUS_HEALTH_QUERY


class PrometheusClientError(Exception):
    """Base exception for Prometheus client failures."""


class PrometheusHTTPError(PrometheusClientError):
    """Raised when Prometheus returns non-success HTTP responses."""


class PrometheusResponseError(PrometheusClientError):
    """Raised when Prometheus response payload is malformed."""


class PrometheusClient:
    """Wrapper around Prometheus query and query_range endpoints."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
        )

    async def __aenter__(self) -> "PrometheusClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_client:
            await self._client.aclose()

    async def query(
        self,
        query: str,
        at_time: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """Run an instant query against Prometheus."""
        params: Dict[str, str] = {"query": query}
        if at_time is not None:
            params["time"] = at_time.isoformat() if isinstance(at_time, datetime) else str(at_time)
        return await self._request("/api/v1/query", params)

    async def query_range(
        self,
        query: str,
        start: Union[str, datetime],
        end: Union[str, datetime],
        step: str,
    ) -> Dict[str, Any]:
        """Run a range query against Prometheus."""
        params = {
            "query": query,
            "start": start.isoformat() if isinstance(start, datetime) else str(start),
            "end": end.isoformat() if isinstance(end, datetime) else str(end),
            "step": step,
        }
        return await self._request("/api/v1/query_range", params)

    async def check_health(self) -> Dict[str, Any]:
        """Check Prometheus connectivity using an API query."""
        try:
            data = await self.query(PROMETHEUS_HEALTH_QUERY)
        except PrometheusClientError as exc:
            return {"healthy": False, "reason": str(exc)}

        result = data.get("result", [])
        return {"healthy": True, "result_count": len(result)}

    async def _request(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Execute Prometheus API request and validate response payload."""
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PrometheusHTTPError(
                f"Prometheus returned {exc.response.status_code} for {path}"
            ) from exc
        except httpx.RequestError as exc:
            raise PrometheusClientError(f"Prometheus request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise PrometheusResponseError("Prometheus response is not valid JSON") from exc

        if payload.get("status") != "success":
            raise PrometheusResponseError(
                f"Prometheus query failed with payload status '{payload.get('status')}'"
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise PrometheusResponseError("Prometheus response missing data object")

        return data

