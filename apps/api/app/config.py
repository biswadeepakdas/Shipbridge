from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.secrets import get_secret, get_github_private_key

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = get_secret("DATABASE_URL", default="postgresql+asyncpg://postgres:postgres@localhost:5432/shipbridge")

    # Redis
    redis_url: str = get_secret("REDIS_URL", default="redis://localhost:6379/0")

    # Supabase
    supabase_url: str = get_secret("SUPABASE_URL", default="http://localhost:54321")
    supabase_service_key: str = get_secret("SUPABASE_SERVICE_KEY", default="")

    # Anthropic / OpenAI
    anthropic_api_key: str = get_secret("ANTHROPIC_API_KEY", default="")
    openai_api_key: str = get_secret("OPENAI_API_KEY", default="")

    # Auth
    jwt_secret: str = get_secret("JWT_SECRET", default="change-me-in-production")
    jwt_algorithm: str = "HS256"

    # Temporal
    temporal_url: str = get_secret("TEMPORAL_URL", default="localhost:7233")
    temporal_host: str = get_secret("TEMPORAL_HOST", default="localhost:7233")
    temporal_namespace: str = get_secret("TEMPORAL_NAMESPACE", default="shipbridge")

    # Observability
    otel_exporter_otlp_endpoint: str = get_secret("OTEL_EXPORTER_OTLP_ENDPOINT", default="")
    sentry_dsn: str = get_secret("SENTRY_DSN", default="")

    # App
    environment: str = get_secret("ENVIRONMENT", default="development")
    log_level: str = get_secret("LOG_LEVEL", default="DEBUG")
    api_base_url: str = get_secret("API_BASE_URL", default="http://localhost:8000")
    web_base_url: str = get_secret("WEB_BASE_URL", default="http://localhost:3000")

    # Temporal deployment mode
    use_temporal: bool = True  # Default to true for production-ready fix

    # GitHub App
    github_app_id: str = get_secret("GITHUB_APP_ID", default="")
    github_webhook_secret: str = get_secret("GITHUB_WEBHOOK_SECRET", default="")
    github_private_key: str = get_github_private_key()

    # Salesforce
    salesforce_username: str | None = get_secret("SALESFORCE_USERNAME")
    salesforce_password: str | None = get_secret("SALESFORCE_PASSWORD")
    salesforce_security_token: str | None = get_secret("SALESFORCE_SECURITY_TOKEN")
    salesforce_instance_url: str | None = get_secret("SALESFORCE_INSTANCE_URL")

    # Notion
    notion_api_key: str | None = get_secret("NOTION_API_KEY")

@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
