"""Application configuration and settings.

Load application configuration from environment variables and .env files.
Manages settings for API, database, Loki, Prometheus, and AI models.
"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Your internal Loki (docker-compose)
    LOKI_URL: str = "http://loki:3100"

    # Target cluster credentials (user provides ONE of these)
    KUBECONFIG_PATH: Optional[str] = None   # e.g. /home/user/.kube/config
    K8S_API_URL: Optional[str] = None       # e.g. https://my-cluster:6443
    K8S_TOKEN: Optional[str] = None         # bearer token

    CLUSTER_NAME: str = "default"
    LOG_TAIL_LINES: int = 500

    class Config:
        env_file = ".env"

settings = Settings()
