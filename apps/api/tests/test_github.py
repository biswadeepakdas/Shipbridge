"""Tests for GitHub App integration — webhooks, badge, framework detection, PR comment."""

import hashlib
import hmac
import os

import pytest
from httpx import AsyncClient

from app.services.github import (
    detect_framework,
    format_pr_comment,
    generate_score_badge_svg,
    verify_webhook_signature,
)


# --- Unit tests: framework detection ---

class TestFrameworkDetection:
    def test_detects_langraph_from_config_file(self) -> None:
        assert detect_framework(["src/agent.py", "langgraph.json"]) == "langraph"

    def test_detects_crewai_from_config_file(self) -> None:
        assert detect_framework(["main.py", "crew.yaml"]) == "crewai"

    def test_detects_autogen_from_config_file(self) -> None:
        assert detect_framework(["agent.py", "OAI_CONFIG_LIST"]) == "autogen"

    def test_detects_langraph_from_requirements(self) -> None:
        files = ["requirements.txt", "main.py"]
        contents = {"requirements.txt": "langgraph==0.1.0\nhttpx"}
        assert detect_framework(files, contents) == "langraph"

    def test_detects_crewai_from_pyproject(self) -> None:
        files = ["pyproject.toml"]
        contents = {"pyproject.toml": '[dependencies]\ncrewai = "^0.30"'}
        assert detect_framework(files, contents) == "crewai"

    def test_detects_autogen_from_imports(self) -> None:
        files = ["agent.py"]
        contents = {"agent.py": "from autogen import AssistantAgent"}
        assert detect_framework(files, contents) == "autogen"

    def test_returns_custom_when_no_framework_found(self) -> None:
        assert detect_framework(["main.py", "utils.py"]) == "custom"

    def test_returns_custom_for_empty_file_list(self) -> None:
        assert detect_framework([]) == "custom"

    def test_detects_from_path_patterns(self) -> None:
        assert detect_framework(["src/langgraph/agent.py"]) == "langraph"


# --- Unit tests: SVG badge ---

class TestBadgeSvg:
    def test_badge_contains_score(self) -> None:
        svg = generate_score_badge_svg(72)
        assert "72" in svg
        assert "readiness" in svg

    def test_badge_green_above_75(self) -> None:
        svg = generate_score_badge_svg(80)
        assert "#2A9D6E" in svg

    def test_badge_yellow_between_50_75(self) -> None:
        svg = generate_score_badge_svg(60)
        assert "#C49A3C" in svg

    def test_badge_red_below_50(self) -> None:
        svg = generate_score_badge_svg(30)
        assert "#C44A4A" in svg

    def test_badge_is_valid_svg(self) -> None:
        svg = generate_score_badge_svg(72)
        assert svg.startswith("<svg")
        assert svg.strip().endswith("</svg>")


# --- Unit tests: PR comment ---

class TestPRComment:
    def test_comment_contains_score(self) -> None:
        md = format_pr_comment(72, {
            "reliability": {"score": 80, "status": "ok"},
            "security": {"score": 60, "status": "warn"},
        }, {"total_issues": 2, "critical_count": 1, "estimated_effort_days": 3})
        assert "72/100" in md
        assert "BLOCKED" in md

    def test_passing_score_shows_pass(self) -> None:
        md = format_pr_comment(80, {
            "reliability": {"score": 80, "status": "ok"},
        }, {"total_issues": 0})
        assert "PASS" in md

    def test_delta_shown_when_previous_score(self) -> None:
        md = format_pr_comment(75, {}, {"total_issues": 0}, previous_score=70)
        assert "+5" in md

    def test_negative_delta(self) -> None:
        md = format_pr_comment(65, {}, {"total_issues": 1, "critical_count": 0, "estimated_effort_days": 1, "blockers": []}, previous_score=70)
        assert "-5" in md

    def test_contains_pillar_table(self) -> None:
        md = format_pr_comment(72, {
            "reliability": {"score": 80, "status": "ok"},
            "security": {"score": 60, "status": "warn"},
        }, {"total_issues": 0})
        assert "Reliability" in md
        assert "Security" in md
        assert "| 80 |" in md

    def test_shows_top_blockers(self) -> None:
        md = format_pr_comment(50, {}, {
            "total_issues": 1,
            "critical_count": 1,
            "estimated_effort_days": 2,
            "blockers": [{"severity": "high", "title": "No auth", "fix_hint": "Add OAuth"}],
        })
        assert "No auth" in md
        assert "Add OAuth" in md


# --- Unit tests: webhook signature verification ---

class TestWebhookSignature:
    def test_valid_signature_passes(self) -> None:
        os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
        from app.config import get_settings
        get_settings.cache_clear()
        payload = b'{"action":"opened"}'
        sig = "sha256=" + hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(payload, sig) is True
        # Restore
        os.environ["GITHUB_WEBHOOK_SECRET"] = ""
        get_settings.cache_clear()

    def test_invalid_signature_fails(self) -> None:
        os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
        from app.config import get_settings
        get_settings.cache_clear()
        payload = b'{"action":"opened"}'
        assert verify_webhook_signature(payload, "sha256=invalid") is False
        os.environ["GITHUB_WEBHOOK_SECRET"] = ""
        get_settings.cache_clear()


# --- API endpoint tests ---

@pytest.mark.asyncio
async def test_webhook_endpoint_accepts_valid_payload(client: AsyncClient) -> None:
    """Webhook endpoint processes a valid GitHub push event."""
    resp = await client.post(
        "/webhooks/github",
        json={"action": "opened", "repository": {"full_name": "acme/agent"}},
        headers={"X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["event_type"] == "push"
    assert data["repo_full_name"] == "acme/agent"
    assert data["processed"] is True


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(client: AsyncClient) -> None:
    """Webhook endpoint rejects payload with invalid HMAC signature."""
    os.environ["GITHUB_WEBHOOK_SECRET"] = "real-secret"
    resp = await client.post(
        "/webhooks/github",
        json={"action": "opened"},
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=definitelywrong",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_badge_returns_svg(client: AsyncClient) -> None:
    """Badge endpoint returns valid SVG for any project ID."""
    resp = await client.get("/badge/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert resp.text.startswith("<svg")


@pytest.mark.asyncio
async def test_badge_shows_score_after_assessment(client: AsyncClient) -> None:
    """Badge reflects latest assessment score."""
    # Signup and create project with assessment
    signup = await client.post("/api/v1/auth/signup", json={
        "email": "badge@test.com", "full_name": "Badge User",
        "tenant_name": "Badge Corp", "tenant_slug": "badge-corp",
    })
    token = signup.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/api/v1/projects", headers=headers, json={
        "name": "Badge Agent", "framework": "langraph",
        "stack_json": {"models": ["sonnet", "haiku"], "tools": ["sf"], "deployment": "railway"},
    })
    project_id = proj.json()["data"]["id"]
    await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)

    # Check badge
    resp = await client.get(f"/badge/{project_id}")
    assert resp.status_code == 200
    assert "readiness" in resp.text


@pytest.mark.asyncio
async def test_detect_framework_endpoint(client: AsyncClient) -> None:
    """Framework detection endpoint identifies LangGraph from requirements."""
    resp = await client.post("/api/v1/github/detect-framework", json={
        "file_list": ["requirements.txt", "main.py"],
        "file_contents": {"requirements.txt": "langgraph==0.2.0\nhttpx"},
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["framework"] == "langraph"


@pytest.mark.asyncio
async def test_pr_comment_preview_endpoint(client: AsyncClient) -> None:
    """PR comment preview returns markdown with score and pillars."""
    resp = await client.post("/api/v1/github/pr-comment-preview", json={
        "total_score": 72,
        "pillars": {
            "reliability": {"score": 80, "status": "ok"},
            "security": {"score": 60, "status": "warn"},
        },
        "gap_report": {"total_issues": 2, "critical_count": 1, "estimated_effort_days": 3,
                        "blockers": [{"severity": "high", "title": "No auth", "fix_hint": "Add OAuth"}]},
    })
    assert resp.status_code == 200
    md = resp.json()["data"]["markdown"]
    assert "72/100" in md
    assert "No auth" in md
