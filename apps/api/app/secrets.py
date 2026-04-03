import os
from typing import Optional

import structlog

logger = structlog.get_logger()

def get_secret(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Retrieves a secret from environment variables.

    In a production environment, this function would be extended to fetch secrets
    from a secure secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault).
    """
    value = os.getenv(key, default)
    if required and value is None:
        logger.error("secret_missing", key=key, message="Required secret is not set in environment variables.")
        raise ValueError(f"Required secret '{key}' is not set.")
    elif value is None:
        logger.warning("secret_not_set", key=key, message="Optional secret is not set in environment variables.")
    return value


def get_github_private_key() -> str:
    """Retrieves the GitHub App private key, handling multiline format."""
    key = get_secret("GITHUB_PRIVATE_KEY", default="")
    return key.replace("\\n", "\n") if key else ""
