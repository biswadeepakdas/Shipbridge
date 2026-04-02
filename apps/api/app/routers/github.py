import uuid
import json

import structlog
from fastapi import APIRouter, Header, Request, Depends, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.exceptions import AppError, ErrorCode
from app.models.projects import AssessmentRun, Project
from app.schemas.response import APIResponse
from app.services.github import (
    detect_framework,
    format_pr_comment,
    generate_score_badge_svg,
    verify_webhook_signature,
    github_app_service
)
from app.os_layer.event_ingestion import EventIngestionSubsystem

logger = structlog.get_logger()

router = APIRouter(tags=["github"])


# --- Webhook Receiver ---

class WebhookEvent(BaseModel):
    """Parsed GitHub webhook event summary."""

    event_type: str
    action: str | None
    repo_full_name: str | None
    processed: bool


async def process_github_webhook_background(payload: bytes, event_type: str, delivery_id: str, db: AsyncSession):
    """Background task to process GitHub webhooks asynchronously."""
    body = json.loads(payload)
    action = body.get("action")
    repo = body.get("repository", {})
    repo_full_name = repo.get("full_name")
    pull_request = body.get("pull_request", {})
    pull_number = pull_request.get("number")

    logger.info(
        "github_webhook_processing_background",
        event_type=event_type,
        action=action,
        repo=repo_full_name,
        pull_number=pull_number,
        delivery_id=delivery_id
    )

    # Link GitHub repo to a ShipBridge project
    # This assumes a project can be identified by its linked GitHub repository full name
    project_result = await db.execute(
        select(Project).where(Project.github_repo_full_name == repo_full_name)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        logger.warning("no_shipbridge_project_linked", repo=repo_full_name, message="No ShipBridge project linked to this GitHub repository.")
        return

    # Example: Post PR comment on pull_request opened/synchronize
    if event_type == "pull_request" and action in ["opened", "synchronize"] and pull_number:
        # Fetch the latest assessment run for the linked project
        assessment_result = await db.execute(
            select(AssessmentRun)
            .where(AssessmentRun.project_id == project.id, AssessmentRun.status == "complete")
            .order_by(AssessmentRun.created_at.desc()).limit(1)
        )
        assessment = assessment_result.scalar_one_or_none()

        if assessment:
            comment_body = format_pr_comment(
                assessment.total_score,
                assessment.scores_json, # Assuming scores_json contains pillar data
                assessment.gap_report_json,
                assessment.previous_total_score # Assuming this field exists or can be derived
            )
            await github_app_service.post_pr_comment(repo_full_name, pull_number, comment_body)
        else:
            logger.warning("no_assessment_found_for_pr", project_id=project.id, repo=repo_full_name, pull_number=pull_number, message="No completed assessment found for this project.")


@router.post("/webhooks/github", response_model=APIResponse[WebhookEvent])
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    db: AsyncSession = Depends(get_db)
) -> APIResponse[WebhookEvent]:
    """Receive and verify GitHub webhook events.

    Verifies X-Hub-Signature-256 before processing. Queues heavy processing to background tasks.
    """
    payload = await request.body()

    # Verify HMAC signature if webhook secret is configured
    if x_hub_signature_256:
        if not verify_webhook_signature(payload, x_hub_signature_256):
            raise AppError(ErrorCode.FORBIDDEN, "Invalid webhook signature")

    event_type = x_github_event or "unknown"
    delivery_id = x_github_delivery or str(uuid.uuid4())

    logger.info(
        "github_webhook_received_sync",
        event_type=event_type,
        delivery_id=delivery_id,
        message="Webhook received, queuing for background processing."
    )

    # Queue heavy processing to a background task
    background_tasks.add_task(process_github_webhook_background, payload, event_type, delivery_id, db)

    return APIResponse(
        data=WebhookEvent(
            event_type=event_type,
            action="queued", # Indicate that it's queued
            repo_full_name=None, # Not parsed in sync part
            processed=True,
        )
    )


# --- Badge Endpoint ---

@router.get("/badge/{project_id}")
async def readiness_badge(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """SVG readiness score badge for GitHub README embedding.

    Public endpoint — no auth required. Returns the latest assessment score.
    """
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        return Response(
            content=generate_score_badge_svg(0, "invalid"),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.project_id == pid, AssessmentRun.status == "complete")
        .order_by(AssessmentRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()

    if not run:
        svg = generate_score_badge_svg(0, "no data")
    else:
        svg = generate_score_badge_svg(run.total_score)

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "max-age=300"},
    )


# --- Framework Detection ---

class FrameworkDetectionRequest(BaseModel):
    """Request to detect framework from file list."""

    file_list: list[str]
    file_contents: dict[str, str] | None = None


class FrameworkDetectionResult(BaseModel):
    """Detected framework result."""

    framework: str


@router.post("/api/v1/github/detect-framework", response_model=APIResponse[FrameworkDetectionResult])
async def detect_framework_endpoint(
    body: FrameworkDetectionRequest,
) -> APIResponse[FrameworkDetectionResult]:
    """Auto-detect AI agent framework from repository file list and contents."""
    framework = detect_framework(body.file_list, body.file_contents)
    return APIResponse(data=FrameworkDetectionResult(framework=framework))


# --- PR Comment Preview ---

class PRCommentRequest(BaseModel):
    """Request to generate a PR comment from assessment data."""

    total_score: int
    pillars: dict[str, dict]
    gap_report: dict
    previous_score: int | None = None


class PRCommentResult(BaseModel):
    """Generated PR comment markdown."""

    markdown: str


@router.post("/api/v1/github/pr-comment-preview", response_model=APIResponse[PRCommentResult])
async def preview_pr_comment(
    body: PRCommentRequest,
) -> APIResponse[PRCommentResult]:
    """Generate a preview of the PR comment that would be posted."""
    markdown = format_pr_comment(
        body.total_score,
        body.pillars,
        body.gap_report,
        body.previous_score,
    )
    return APIResponse(data=PRCommentResult(markdown=markdown))
