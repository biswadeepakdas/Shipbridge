import hmac
import hashlib
import json
from typing import Any, Dict, List, Optional

from github import Github, Auth
from github.AuthenticatedUser import AuthenticatedUser
from github.Installation import Installation
from github.Repository import Repository
import structlog

from app.config import get_settings

logger = structlog.get_logger()

# Framework detection patterns — maps file/config patterns to framework names
FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "langchain": ["langchain", "langchain_core", "langchain_community"],
    "llamaindex": ["llama_index"],
    "autogen": ["autogen"],
    "crewai": ["crewai"],
    "fastapi": ["fastapi", "uvicorn"],
    "flask": ["flask"],
    "django": ["django"],
    "react": ["react", "next.js", "vite"],
    "angular": ["angular", "@angular/core"],
    "vue": ["vue"],
}

# Files that indicate specific frameworks
FRAMEWORK_FILES: dict[str, str] = {
    "langgraph.json": "langraph",
    "crew.yaml": "crewai",
    "crewai.yaml": "crewai",
    "OAI_CONFIG_LIST": "autogen",
}

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify the GitHub webhook signature."""
    settings = get_settings()
    if not settings.github_webhook_secret:
        logger.warning("github_webhook_secret_missing", message="GitHub webhook secret is not configured. Skipping signature verification.")
        return True # Allow if secret is not set (dev/test)

    try:
        sha_name, signature_hash = signature.split("=", 1)
        if sha_name != "sha256":
            return False
        
        mac = hmac.new(settings.github_webhook_secret.encode(), msg=payload, digestmod=hashlib.sha256)
        return hmac.compare_digest(mac.hexdigest(), signature_hash)
    except Exception as e:
        logger.error("github_signature_verification_failed", error=str(e))
        return False

class GitHubAppService:
    """Service for interacting with GitHub as a GitHub App."""
    def __init__(self):
        settings = get_settings()
        if not settings.github_app_id or not settings.github_private_key:
            logger.error("github_app_credentials_missing", message="GitHub App ID or private key is missing. GitHub App functionality will be limited.")
            self.app_id = None
            self.private_key = None
        else:
            self.app_id = int(settings.github_app_id)
            self.private_key = settings.github_private_key.replace("\\n", "\n") # Handle multiline private key

        self._integration = None

    def _get_integration(self):
        if not self._integration:
            if not self.app_id or not self.private_key:
                raise ValueError("GitHub App credentials not configured.")
            auth = Auth.AppAuth(self.app_id, self.private_key)
            self._integration = Github(auth=auth)
        return self._integration

    def get_installation_client(self, installation_id: int) -> Github:
        """Returns a PyGithub client authenticated as an installation."""
        integration = self._get_integration()
        auth = Auth.InstallationAuth(integration.get_app().get_installation(installation_id).get_access_token().token)
        return Github(auth=auth)

    def get_repo_installation(self, repo_full_name: str) -> Optional[Installation]:
        """Finds the installation for a given repository."""
        integration = self._get_integration()
        for installation in integration.get_app().get_installations():
            for repo in installation.get_repos():
                if repo.full_name == repo_full_name:
                    return installation
        return None

    async def post_pr_comment(self, repo_full_name: str, pull_number: int, comment_body: str) -> bool:
        """Posts a comment to a pull request."""
        installation = self.get_repo_installation(repo_full_name)
        if not installation:
            logger.warning("github_installation_not_found", repo=repo_full_name, message="No GitHub App installation found for repository.")
            return False

        try:
            installation_client = self.get_installation_client(installation.id)
            repo = installation_client.get_repo(repo_full_name)
            pull = repo.get_pull(pull_number)
            pull.create_issue_comment(comment_body)
            logger.info("github_pr_comment_posted", repo=repo_full_name, pull_number=pull_number)
            return True
        except Exception as e:
            logger.error("github_pr_comment_failed", repo=repo_full_name, pull_number=pull_number, error=str(e))
            return False

github_app_service = GitHubAppService()

def detect_framework(file_list: List[str], file_contents: Optional[Dict[str, str]] = None) -> str:
    """Auto-detect AI agent framework from repository file list and contents."""
    # ... (existing implementation) ...
    FRAMEWORK_PATTERNS = {
        "langchain": ["langchain", "langchain_core", "langchain_community"],
        "llamaindex": ["llama_index"],
        "autogen": ["autogen"],
        "crewai": ["crewai"],
        "fastapi": ["fastapi", "uvicorn"],
        "flask": ["flask"],
        "django": ["django"],
        "react": ["react", "next.js", "vite"],
        "angular": ["angular", "@angular/core"],
        "vue": ["vue"],
    }

    FRAMEWORK_FILES = {
        "langchain": ["chain.py", "agent.py", "langchain_helper.py"],
        "llamaindex": ["query_engine.py", "index.py"],
        "autogen": ["agent_workflow.py"],
        "crewai": ["crew.py", "agent.py", "task.py"],
        "fastapi": ["main.py", "app.py"],
        "flask": ["app.py"],
        "django": ["manage.py", "settings.py"],
        "react": ["package.json", "vite.config.js", "next.config.js"],
        "angular": ["angular.json", "main.ts"],
        "vue": ["vue.config.js", "main.js"],
    }

    detected_frameworks = set()

    # Check file names
    for file_name in file_list:
        for framework, patterns in FRAMEWORK_FILES.items():
            if any(p in file_name.lower() for p in patterns):
                detected_frameworks.add(framework)

    # Check file contents
    if file_contents:
        for path, content in file_contents.items():
            for framework, patterns in FRAMEWORK_PATTERters.items():
                if any(p in content for p in patterns):
                    detected_frameworks.add(framework)

    if detected_frameworks:
        # Prioritize more specific frameworks or common ones
        if "langchain" in detected_frameworks: return "langchain"
        if "llamaindex" in detected_frameworks: return "llamaindex"
        if "autogen" in detected_frameworks: return "autogen"
        if "crewai" in detected_frameworks: return "crewai"
        if "fastapi" in detected_frameworks: return "fastapi"
        if "flask" in detected_frameworks: return "flask"
        if "django" in detected_frameworks: return "django"
        if "react" in detected_frameworks: return "react"
        if "angular" in detected_frameworks: return "angular"
        if "vue" in detected_frameworks: return "vue"
        return sorted(list(detected_frameworks))[0] # Fallback to alphabetical
    return "unknown"

def generate_score_badge_svg(score: int, label: str = "readiness") -> str:
    """Generates an SVG badge for the given score."""
    color = "#4c1" if score >= 75 else ("#fe7d37" if score >= 50 else "#e05d44")
    message = f"{score}/100"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20">
  <linearGradient id="a" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <rect rx="3" width="100" height="20" fill="#555"/>
  <rect rx="3" x="{len(label)*6+10}" width="{len(message)*6+10}" height="20" fill="{color}"/>
  <path fill="{color}" d="M{len(label)*6+10} 0h4v20h-4z"/>
  <rect rx="3" width="100" height="20" fill="url(#a)"/>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{len(label)*3+5}" y="14" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{len(label)*3+5}" y="13">{label}</text>
    <text x="{len(label)*6+10 + len(message)*3+5}" y="14" fill="#010101" fill-opacity=".3">{message}</text>
    <text x="{len(label)*6+10 + len(message)*3+5}" y="13">{message}</text>
  </g>
</svg>"""

def format_pr_comment(total_score: int, pillars: Dict[str, Any], gap_report: Dict[str, Any], previous_score: Optional[int] = None) -> str:
    """Formats a GitHub PR comment with assessment results."""
    status_emoji = "✅" if total_score >= 75 else "⚠️"
    status_text = "Production Ready" if total_score >= 75 else "Review Required"

    score_change = ""
    if previous_score is not None:
        diff = total_score - previous_score
        if diff > 0:
            score_change = f" (⬆️ +{diff})"
        elif diff < 0:
            score_change = f" (⬇️ {diff})"

    comment = f"{status_emoji} **ShipBridge Readiness: {total_score}/100**{score_change} - {status_text}\n\n"
    comment += "This pull request has been assessed for production readiness.\n\n"

    comment += "### 5-Pillar Scorecard\n"
    comment += "| Pillar | Score | Status | Issues |\n"
    comment += "|--------|-------|--------|--------|\n"
    for name, data in pillars.items():
        score = data.get("score", 0)
        status = data.get("status", "unknown")
        issues_count = len(data.get("issues", []))
        comment += f"| {name.capitalize()} | {score} | {status.upper()} | {issues_count} |\n"
    comment += "\n"

    blockers = gap_report.get("blockers", [])
    if blockers:
        comment += "### Identified Gaps / Blockers\n"
        for b in blockers[:5]: # Limit to top 5 blockers for brevity in PR comment
            comment += f"- **[{b.get('severity', '').upper()}]** {b.get('title', '')} — {b.get('fix_hint', '')}\n"
        comment += "\n"

    comment += f"_For a full report, see the [ShipBridge dashboard]({get_settings().web_base_url})._\n"
    return comment
