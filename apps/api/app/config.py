"""Application configuration via environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/shipbridge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Supabase
    supabase_url: str = "http://localhost:54321"
    supabase_service_key: str = ""

    # Anthropic / OpenAI
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # Temporal
    temporal_url: str = "localhost:7233"
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "shipbridge"

    # Observability
    otel_exporter_otlp_endpoint: str = ""
    sentry_dsn: str = ""

    # App
    environment: str = "development"
    log_level: str = "DEBUG"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"

    # Temporal deployment mode
    use_temporal: bool = True  # Default to true for production-ready fix

    # GitHub App
    github_app_id: str = ""
    github_webhook_secret: str = ""
    github_private_key: str = ""

@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
