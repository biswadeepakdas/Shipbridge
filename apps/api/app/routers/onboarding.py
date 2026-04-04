"""Onboarding routes — wizard steps, framework options, quick-start, repo ingestion."""

import re
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.middleware.auth import AuthContext, get_auth_context
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.services.onboarding import (
    OnboardingResult,
    OnboardingStep,
    get_framework_options,
    get_onboarding_steps,
    get_sample_config,
    run_onboarding_assessment,
)

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

# Model name patterns found in code
_MODEL_PATTERNS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
    "claude-opus-4", "claude-sonnet-4", "claude-haiku-4", "claude-3-5-sonnet",
    "claude-3-opus", "claude-3-haiku", "gemini-1.5-pro", "gemini-1.5-flash",
    "gemini-pro", "llama-3", "mistral", "mixtral",
]

# Tool/integration patterns
_TOOL_PATTERNS = {
    "web_search": ["tavily", "serper", "serpapi", "duckduckgo", "googlesearch"],
    "code_executor": ["e2b", "codeinterpreter", "jupyter", "subprocess"],
    "file_reader": ["pathlib", "open(", "FileIO", "pdfminer", "pypdf"],
    "email_sender": ["smtplib", "sendgrid", "mailgun", "resend"],
    "slack_notify": ["slack_sdk", "slack_bolt", "SlackClient"],
    "knowledge_base_search": ["pinecone", "weaviate", "qdrant", "chromadb", "faiss"],
    "api_caller": ["requests", "httpx", "aiohttp"],
    "web_browser": ["playwright", "selenium", "puppeteer", "browsing"],
    "github": ["github", "PyGithub", "gitpython"],
    "notion": ["notion_client", "notionhq"],
    "data_retriever": ["sqlalchemy", "psycopg", "pymongo", "elasticsearch"],
}

# Security patterns
_AUTH_PATTERNS = {
    "jwt": ["jwt", "PyJWT", "jose", "JsonWebToken"],
    "oauth2": ["oauth2", "authlib", "OAuth2"],
    "api_key": ["api_key", "X-API-Key", "apikey"],
    "basic": ["BasicAuth", "HTTPBasicCredentials"],
}


def _parse_github_url(repo_url: str) -> tuple[str, str] | None:
    """Extract owner/repo from a GitHub URL. Returns None if invalid."""
    patterns = [
        r"github\.com[/:]([^/]+)/([^/\.\s]+?)(?:\.git)?$",
        r"github\.com[/:]([^/]+)/([^/\.\s]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, repo_url)
        if m:
            return m.group(1), m.group(2).rstrip("/")
    return None


async def _fetch_github_file(client: httpx.AsyncClient, owner: str, repo: str, path: str, headers: dict) -> str | None:
    """Fetch raw content of a file from GitHub API."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("encoding") == "base64":
                import base64
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None
    except Exception:
        return None


async def _ingest_repo(repo_url: str) -> dict:
    """Fetch a GitHub repo's key files and build a real stack_json."""
    from app.services.github import detect_framework

    parsed = _parse_github_url(repo_url)
    if not parsed:
        return {}
    owner, repo = parsed

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ShipBridge/1.0",
    }
    # Use token if available
    from app.config import get_settings
    settings = get_settings()
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    async with httpx.AsyncClient() as client:
        # Get repo tree (recursive)
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        tree_r = await client.get(tree_url, headers=headers, timeout=15)
        if tree_r.status_code != 200:
            return {}

        tree_data = tree_r.json()
        all_paths = [item["path"] for item in tree_data.get("tree", []) if item["type"] == "blob"]

        # Key files to fetch for analysis
        priority_files = [
            "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
            "package.json", ".env.example", ".github/workflows/ci.yml",
            ".github/workflows/main.yml", "docker-compose.yml", "Dockerfile",
            "crew.py", "agent.py", "main.py", "app.py", "config.py",
        ]
        # Also grab any .py files at root level or in src/
        for path in all_paths:
            parts = path.split("/")
            if path.endswith(".py") and (len(parts) <= 2 or parts[0] in ("src", "app", "agent", "agents")):
                if path not in priority_files:
                    priority_files.append(path)

        # Fetch up to 15 files concurrently
        fetch_targets = [p for p in priority_files if p in all_paths][:15]
        tasks = [_fetch_github_file(client, owner, repo, path, headers) for path in fetch_targets]
        import asyncio
        contents_list = await asyncio.gather(*tasks)
        file_contents = {path: content for path, content in zip(fetch_targets, contents_list) if content}

    # Combine all content for analysis
    all_content = "\n".join(file_contents.values())

    # Detect framework
    detected_fw = detect_framework(all_paths, file_contents)
    # Map to our onboarding framework IDs
    fw_map = {
        "crewai": "crewai", "autogen": "autogen", "langchain": "langraph",
        "llamaindex": "langraph", "fastapi": "custom", "unknown": "custom",
    }
    framework = fw_map.get(detected_fw, "custom")

    # Detect models used
    models_used = [m for m in _MODEL_PATTERNS if m in all_content]

    # Detect tools
    tools_used = [tool for tool, patterns in _TOOL_PATTERNS.items()
                  if any(p in all_content for p in patterns)]

    # Detect auth type
    auth_type = "none"
    auth_provider = "custom"
    for atype, patterns in _AUTH_PATTERNS.items():
        if any(p in all_content for p in patterns):
            auth_type = atype
            break
    if "supabase" in all_content:
        auth_provider = "supabase"
    elif "auth0" in all_content.lower():
        auth_provider = "auth0"

    # Detect deployment
    deployment = "custom"
    if "railway" in all_content.lower():
        deployment = "railway"
    elif "dockerfile" in all_content.lower() or "docker-compose" in all_content.lower():
        deployment = "docker"
    elif "vercel" in all_content.lower():
        deployment = "vercel"
    elif "render.com" in all_content.lower():
        deployment = "render"

    # Detect test coverage proxy (presence of test files)
    test_files = [p for p in all_paths if "/test" in p or p.startswith("test") or "spec." in p]
    ci_files = [p for p in all_paths if ".github/workflows" in p or "gitlab-ci" in p]
    has_ci = len(ci_files) > 0
    has_tests = len(test_files) > 0
    # Rough coverage estimate based on ratio of test files
    test_coverage = min(90, max(10, len(test_files) * 5)) if has_tests else 0

    # Security patterns
    injection_guard = any(kw in all_content for kw in ["injection", "sanitize", "escape", "guard"])
    audit_trail = any(kw in all_content for kw in ["audit", "log_event", "audit_log", "structlog"])
    hitl_gates = any(kw in all_content for kw in ["human_in_the_loop", "hitl", "approval", "human_approval", "interrupt"])
    mcp_endpoints_raw = re.findall(r'["\'](/tools/[^"\']+)["\']', all_content)
    mcp_auth = "mcp_auth" in all_content or ("mcp" in all_content and auth_type != "none")

    stack_json: dict = {
        "repo_url": repo_url,
        "detected_framework": detected_fw,
        "models": models_used or ["gpt-4o-mini"],
        "tools": tools_used,
        "deployment": deployment,
        "test_coverage": test_coverage,
        "has_ci": has_ci,
        "injection_guard": injection_guard,
        "audit_trail": audit_trail,
        "hitl_gates": hitl_gates,
    }
    if auth_type != "none":
        stack_json["auth"] = {"type": auth_type, "provider": auth_provider}
    if mcp_endpoints_raw:
        stack_json["mcp_endpoints"] = list(set(mcp_endpoints_raw))[:5]
        stack_json["mcp_auth"] = mcp_auth

    return stack_json


class IngestRepoRequest(BaseModel):
    """Request to ingest a GitHub repository for assessment."""
    repo_url: str


class IngestRepoResult(BaseModel):
    """Result of ingesting a GitHub repository."""
    repo_url: str
    detected_framework: str
    stack_json: dict


class QuickStartRequest(BaseModel):
    """Request to complete onboarding in one step."""

    project_name: str
    framework: str = "custom"
    stack_json: dict | None = None


@router.get("/steps", response_model=APIResponse[list[OnboardingStep]])
async def get_steps() -> APIResponse[list[OnboardingStep]]:
    """Get onboarding wizard steps."""
    return APIResponse(data=get_onboarding_steps())


@router.get("/frameworks", response_model=APIResponse[list[dict]])
async def list_frameworks() -> APIResponse[list[dict]]:
    """List available agent frameworks with descriptions."""
    return APIResponse(data=get_framework_options())


@router.get("/sample-config/{framework}", response_model=APIResponse[dict])
async def sample_config(framework: str) -> APIResponse[dict]:
    """Get a sample stack configuration for a framework."""
    config = get_sample_config(framework)
    return APIResponse(data={"framework": framework, "stack_json": config})


@router.post("/ingest-repo", response_model=APIResponse[IngestRepoResult])
async def ingest_repo(body: IngestRepoRequest) -> APIResponse[IngestRepoResult]:
    """Ingest a GitHub repository and extract a real stack_json for assessment."""
    stack_json = await _ingest_repo(body.repo_url)
    if not stack_json:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.VALIDATION, "Could not parse repository URL or fetch repository data. Make sure it is a public GitHub repo.")
    return APIResponse(data=IngestRepoResult(
        repo_url=body.repo_url,
        detected_framework=stack_json.get("detected_framework", "unknown"),
        stack_json=stack_json,
    ))


@router.post("/quick-start", response_model=APIResponse[OnboardingResult])
async def quick_start(
    body: QuickStartRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[OnboardingResult]:
    """Complete onboarding: create project + run first assessment in one step."""
    stack_json = body.stack_json or get_sample_config(body.framework)

    # Create project
    project = Project(
        tenant_id=uuid.UUID(auth.tenant_id),
        name=body.project_name,
        framework=body.framework,
        stack_json=stack_json,
    )
    db.add(project)
    await db.flush()

    # Run assessment
    result = run_onboarding_assessment(stack_json, body.framework)
    result.project_id = str(project.id)
    result.project_name = body.project_name

    # Store assessment
    from app.assessment.runner import AssessmentRunner
    runner = AssessmentRunner()
    assessment = runner.run(stack_json, body.framework)

    run = AssessmentRun(
        project_id=project.id,
        tenant_id=uuid.UUID(auth.tenant_id),
        total_score=assessment.total_score,
        scores_json={k: v.model_dump() for k, v in assessment.pillars.items()},
        gap_report_json=assessment.gap_report.model_dump(),
        status="complete",
        triggered_by="onboarding",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()

    return APIResponse(data=result)
