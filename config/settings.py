from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loaded from environment variables or a .env file.
    All fields have safe defaults for local dev.
    """

    # Loki
    loki_url: str = "http://localhost:3100"

    # Kubernetes — comma-separated list used by background collectors
    k8s_watch_namespaces: str = "default"

    # Ingestion defaults
    log_since_seconds: int = 3600
    log_tail_lines: int = 500

    # App
    app_name: str = "k8s-ai-incident-analyzer"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",    extra="allow"  )

    @property
    def watch_namespaces(self) -> list[str]:
        """Return the namespace list as a Python list."""
        return [ns.strip() for ns in self.k8s_watch_namespaces.split(",") if ns.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()