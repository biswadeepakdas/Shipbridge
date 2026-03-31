"""Environment variable validation script."""

import os
import sys

REQUIRED_VARS = [
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
]

OPTIONAL_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "ANTHROPIC_API_KEY",
    "TEMPORAL_HOST",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "SENTRY_DSN",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "API_BASE_URL",
    "WEB_BASE_URL",
]


def validate() -> bool:
    """Validate that all required environment variables are set."""
    missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return False
    print("All required environment variables are set.")
    for var in OPTIONAL_VARS:
        status = "set" if os.environ.get(var) else "unset"
        print(f"  {var}: {status}")
    return True


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
