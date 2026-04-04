"""Parser for shipbridge.yaml manifest files."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, field_validator


class AgentManifest(BaseModel):
    """Parsed shipbridge.yaml manifest."""

    version: str = "1"
    name: str
    framework: str = "custom"
    description: str = ""
    models: list[str] = []
    tools: list[dict[str, Any]] = []
    connectors: list[dict[str, Any]] = []
    eval_cases: list[dict[str, Any]] = []
    policies: dict[str, Any] = {}
    runtime: dict[str, Any] = {}
    deployment: dict[str, Any] = {}

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class ManifestValidationResult(BaseModel):
    """Result of parsing and validating a manifest."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    manifest: AgentManifest | None = None


def parse_manifest(yaml_content: str) -> ManifestValidationResult:
    """Parse and validate a shipbridge.yaml manifest string."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Parse YAML
    try:
        raw = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return ManifestValidationResult(valid=False, errors=[f"Invalid YAML: {exc}"])

    if not isinstance(raw, dict):
        return ManifestValidationResult(valid=False, errors=["Manifest must be a YAML mapping"])

    # 2. Validate with Pydantic model
    try:
        manifest = AgentManifest(**raw)
    except Exception as exc:
        return ManifestValidationResult(valid=False, errors=[str(exc)])

    # 3. Semantic checks
    if not manifest.models:
        warnings.append("No models listed — scoring will be limited")

    if not manifest.eval_cases:
        warnings.append("No eval_cases — eval pillar score will be reduced")

    if manifest.runtime:
        endpoint = manifest.runtime.get("endpoint", "")
        if endpoint and not (endpoint.startswith("http://") or endpoint.startswith("https://")):
            errors.append(f"runtime.endpoint must be a valid URL, got: {endpoint}")

    if manifest.policies:
        max_lat = manifest.policies.get("max_latency_ms")
        if max_lat is not None and (not isinstance(max_lat, (int, float)) or max_lat <= 0):
            errors.append("policies.max_latency_ms must be a positive number")

    if errors:
        return ManifestValidationResult(valid=False, errors=errors, warnings=warnings)

    return ManifestValidationResult(valid=True, errors=[], warnings=warnings, manifest=manifest)


def manifest_to_stack_json(manifest: AgentManifest) -> dict:
    """Convert a parsed manifest into the stack_json format used by scorers."""
    stack: dict[str, Any] = {
        "models": manifest.models,
        "tools": [t.get("name", "") for t in manifest.tools],
        "deployment": manifest.deployment.get("target", ""),
    }

    # Map policies to stack fields
    if manifest.policies:
        if manifest.policies.get("require_hitl"):
            stack["hitl_gates"] = True
        if manifest.policies.get("max_cost_per_call"):
            stack["token_budget"] = True

    # Map runtime fields
    if manifest.runtime:
        if manifest.runtime.get("auth_type"):
            stack["auth"] = {"type": manifest.runtime["auth_type"]}

    # Map eval cases
    if manifest.eval_cases:
        stack["eval_dataset"] = True
        stack["test_coverage"] = min(80, len(manifest.eval_cases) * 10)

    return stack
