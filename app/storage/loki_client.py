import httpx
import time
from app.models.log_models import EnrichedLog

class LokiClient:
    def __init__(self, base_url: str):
        self.push_url = f"{base_url}/loki/api/v1/push"
        self.query_url = f"{base_url}/loki/api/v1/query_range"

    async def push(self, log: EnrichedLog) -> bool:
        payload = {
            "streams": [{
                "stream": {
                    "pod":       log.pod_name,
                    "namespace": log.namespace,
                    "container": log.container,
                    "severity":  log.severity.value,
                    "cluster":   log.cluster_name,
                },
                "values": [[
                    str(int(log.timestamp.timestamp() * 1e9)),  # nanoseconds
                    log.raw_message
                ]]
            }]
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(self.push_url, json=payload)
            return r.status_code == 204

    async def query(self, namespace: str, since_minutes: int = 10, severity: str = None) -> list[dict]:
        end = int(time.time() * 1e9)
        start = end - (since_minutes * 60 * int(1e9))

        label_filter = f'namespace="{namespace}"'
        if severity:
            label_filter += f', severity="{severity}"'

        params = {
            "query": "{" + label_filter + "}",
            "start": start,
            "end":   end,
            "limit": 1000,
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(self.query_url, params=params)
            r.raise_for_status()
            return r.json()["data"]["result"]