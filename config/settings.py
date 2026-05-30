from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loaded from environment variables or a .env file.
    All fields have safe defaults for local dev.
    """

    # Loki (env: LOKI_URL)
    loki_url: str = Field("http://localhost:3100", env="LOKI_URL")

    # Kubernetes — comma-separated list used by background collectors (env: K8S_WATCH_NAMESPACES)
    k8s_watch_namespaces: str = Field("default", env="K8S_WATCH_NAMESPACES")

    # Ingestion defaults
    log_since_seconds: int = Field(3600, env="LOG_SINCE_SECONDS")
    log_tail_lines: int = Field(500, env="LOG_TAIL_LINES")

    # App
    APP_NAME: str = Field("KubeMind", env="APP_NAME")
    APP_VERSION: str = Field("0.1.0", env="APP_VERSION")
    API_HOST: str = Field("0.0.0.0", env="API_HOST")
    API_PORT: int = Field(8000, env="API_PORT")

    # logging
    log_level: str = Field("INFO", env="LOG_LEVEL")

    # Prometheus / metrics
    PROMETHEUS_URL: str = Field("http://prometheus:9090", env="PROMETHEUS_URL")
    PROMETHEUS_TIMEOUT_SECONDS: float = Field(10.0, env="PROMETHEUS_TIMEOUT_SECONDS")
    PROMETHEUS_DEFAULT_LOOKBACK_MINUTES: int = Field(15, env="PROMETHEUS_DEFAULT_LOOKBACK_MINUTES")
    PROMETHEUS_DEFAULT_STEP: str = Field("15s", env="PROMETHEUS_DEFAULT_STEP")

    # Agent runtime
    MODEL_PROVIDER: str = Field("openai", env="MODEL_PROVIDER")
    MODEL_API_KEY: str = Field("", env="MODEL_API_KEY")
    MODEL_NAME: str = Field("gpt-4o-mini", env="MODEL_NAME")
    GOOGLE_API_KEY: str = Field("", env="GOOGLE_API_KEY")
    OPENAI_API_KEY: str = Field("", env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field("gpt-4o-mini", env="OPENAI_MODEL")
    AGENT_TEMPERATURE: float = Field(0.0, env="AGENT_TEMPERATURE")
    AGENT_MAX_ITERATIONS: int = Field(6, env="AGENT_MAX_ITERATIONS")
    AGENT_VERBOSE: bool = Field(False, env="AGENT_VERBOSE")

    # Convenience namespace value (some code expects `NAMESPACE`)
    NAMESPACE: str = Field("default", env="NAMESPACE")

    # pydantic v2 configuration: load from .env by default
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def watch_namespaces(self) -> list[str]:
        """Return the namespace list as a Python list."""
        return [ns.strip() for ns in self.k8s_watch_namespaces.split(",") if ns.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenience imports: `from config.settings import settings`
settings = get_settings()