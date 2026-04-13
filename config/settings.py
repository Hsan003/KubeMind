"""Application configuration and settings.

Load application configuration from environment variables and .env files.
Manages settings for API, database, Loki, Prometheus, and AI models.
"""
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _to_bool(value: str, default: bool = False) -> bool:
    """Parse boolean environment values safely."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    """Typed runtime settings for KubeMind."""

    APP_NAME: str = "KubeMind"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./incident_analyzer.db"
    LOG_LEVEL: str = "INFO"

    LOKI_URL: str = "http://localhost:3100"
    LOKI_USERNAME: str = ""
    LOKI_PASSWORD: str = ""

    PROMETHEUS_URL: str = "http://localhost:9090"
    PROMETHEUS_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1.0)
    PROMETHEUS_DEFAULT_LOOKBACK_MINUTES: int = Field(default=15, ge=1, le=1440)
    PROMETHEUS_DEFAULT_STEP: str = "30s"

    KUBECONFIG_PATH: Optional[str] = None
    NAMESPACE: str = "default"

    MODEL_PROVIDER: str = "openai"
    MODEL_API_KEY: str = ""
    MODEL_NAME: str = "gpt-4"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings object from process environment and .env."""
        load_dotenv()
        return cls(
            APP_NAME=os.getenv("APP_NAME", "KubeMind"),
            APP_VERSION=os.getenv("APP_VERSION", "0.1.0"),
            DEBUG=_to_bool(os.getenv("DEBUG"), default=False),
            API_HOST=os.getenv("API_HOST", "0.0.0.0"),
            API_PORT=int(os.getenv("API_PORT", "8000")),
            DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./incident_analyzer.db"),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
            LOKI_URL=os.getenv("LOKI_URL", "http://localhost:3100"),
            LOKI_USERNAME=os.getenv("LOKI_USERNAME", ""),
            LOKI_PASSWORD=os.getenv("LOKI_PASSWORD", ""),
            PROMETHEUS_URL=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
            PROMETHEUS_TIMEOUT_SECONDS=float(
                os.getenv("PROMETHEUS_TIMEOUT_SECONDS", "10.0")
            ),
            PROMETHEUS_DEFAULT_LOOKBACK_MINUTES=int(
                os.getenv("PROMETHEUS_DEFAULT_LOOKBACK_MINUTES", "15")
            ),
            PROMETHEUS_DEFAULT_STEP=os.getenv("PROMETHEUS_DEFAULT_STEP", "30s"),
            KUBECONFIG_PATH=os.getenv("KUBECONFIG_PATH"),
            NAMESPACE=os.getenv("NAMESPACE", "default"),
            MODEL_PROVIDER=os.getenv("MODEL_PROVIDER", "openai"),
            MODEL_API_KEY=os.getenv("MODEL_API_KEY", ""),
            MODEL_NAME=os.getenv("MODEL_NAME", "gpt-4"),
        )


settings = Settings.from_env()
