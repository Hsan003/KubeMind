"""Tests for Prometheus HTTP client behavior."""

import httpx
import pytest

from app.ingestion.prometheus_client import (
    PrometheusClient,
    PrometheusHTTPError,
    PrometheusResponseError,
)


@pytest.mark.asyncio
async def test_query_returns_prometheus_data() -> None:
    """Instant queries should return the Prometheus data block."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        return httpx.Response(
            status_code=200,
            json={
                "status": "success",
                "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "1"]}]},
            },
        )

    client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    prom = PrometheusClient(base_url="http://test", client=client)

    data = await prom.query("up")

    assert data["resultType"] == "vector"
    await client.aclose()


@pytest.mark.asyncio
async def test_query_range_raises_on_http_error() -> None:
    """Range query should map HTTP failures to PrometheusHTTPError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, json={"status": "error"})

    client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    prom = PrometheusClient(base_url="http://test", client=client)

    with pytest.raises(PrometheusHTTPError):
        await prom.query_range("up", start="1", end="2", step="30s")

    await client.aclose()


@pytest.mark.asyncio
async def test_query_raises_on_malformed_payload() -> None:
    """Malformed API payload should raise PrometheusResponseError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"status": "success"})

    client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    prom = PrometheusClient(base_url="http://test", client=client)

    with pytest.raises(PrometheusResponseError):
        await prom.query("up")

    await client.aclose()


@pytest.mark.asyncio
async def test_check_health_returns_false_on_failure() -> None:
    """Health check should surface Prometheus connectivity failures."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"status": "error"})

    client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    prom = PrometheusClient(base_url="http://test", client=client)

    health = await prom.check_health()

    assert health["healthy"] is False
    assert "reason" in health
    await client.aclose()

