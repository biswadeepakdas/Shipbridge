"""Validates ingestion source connectivity and correctness."""

from __future__ import annotations

import time

import httpx
import structlog

from app.ingestion.manifest_parser import ManifestValidationResult, parse_manifest

logger = structlog.get_logger()


async def validate_github_repo(repo_url: str) -> dict:
    """Check if a GitHub repo URL is accessible.

    Returns ``{valid, error?, repo_info?}``.
    """
    # Extract owner/repo from URL
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return {"valid": False, "error": "Invalid repo URL format. Expected: https://github.com/owner/repo"}

    owner, repo = parts[-2], parts[-1]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "valid": True,
                    "repo_info": {
                        "full_name": data.get("full_name"),
                        "default_branch": data.get("default_branch"),
                        "language": data.get("language"),
                        "description": data.get("description"),
                        "private": data.get("private", False),
                    },
                }
            if resp.status_code == 404:
                return {"valid": False, "error": f"Repository {owner}/{repo} not found (404)"}
            return {"valid": False, "error": f"GitHub API returned {resp.status_code}"}
    except httpx.TimeoutException:
        return {"valid": False, "error": "GitHub API request timed out"}
    except Exception as exc:
        logger.warning("github_validation_failed", error=str(exc))
        return {"valid": False, "error": str(exc)}


async def validate_runtime_endpoint(
    endpoint_url: str, auth_header: str | None = None
) -> dict:
    """Probe a runtime endpoint for reachability.

    Returns ``{valid, latency_ms, error?}``.
    """
    headers: dict[str, str] = {}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint_url, headers=headers)
            latency_ms = round((time.monotonic() - start) * 1000, 1)

            if resp.status_code < 500:
                return {"valid": True, "latency_ms": latency_ms, "status_code": resp.status_code}
            return {
                "valid": False,
                "latency_ms": latency_ms,
                "error": f"Endpoint returned server error: {resp.status_code}",
            }
    except httpx.TimeoutException:
        return {"valid": False, "error": "Endpoint request timed out (10s)"}
    except httpx.ConnectError:
        return {"valid": False, "error": f"Could not connect to {endpoint_url}"}
    except Exception as exc:
        logger.warning("endpoint_validation_failed", error=str(exc))
        return {"valid": False, "error": str(exc)}


async def validate_manifest(yaml_content: str) -> ManifestValidationResult:
    """Parse and validate a manifest. Delegates to manifest_parser."""
    return parse_manifest(yaml_content)
