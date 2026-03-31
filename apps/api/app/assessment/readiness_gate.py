"""ReadinessGate — blocks deployment if totalScore < 75, generates remediation plan."""

from pydantic import BaseModel

from app.assessment.runner import AssessmentResult
from app.assessment.scorers import Issue


class RemediationStep(BaseModel):
    """A single step in the remediation plan."""

    priority: int
    pillar: str
    issue: Issue
    impact: str  # estimated score gain if fixed


class RemediationPlan(BaseModel):
    """Ordered list of steps to reach production readiness."""

    current_score: int
    target_score: int
    gap: int
    steps: list[RemediationStep]
    estimated_total_days: int
    can_deploy: bool


THRESHOLD = 75


def evaluate_readiness(result: AssessmentResult) -> RemediationPlan:
    """Evaluate readiness and generate remediation plan if below threshold."""
    if result.passed:
        return RemediationPlan(
            current_score=result.total_score,
            target_score=THRESHOLD,
            gap=0,
            steps=[],
            estimated_total_days=0,
            can_deploy=True,
        )

    # Build prioritized remediation steps from worst-scoring pillars
    steps: list[RemediationStep] = []
    pillar_scores = sorted(result.pillars.items(), key=lambda x: x[1].score)

    priority = 1
    for pillar_name, pillar_score in pillar_scores:
        for issue in pillar_score.issues:
            # Estimate impact: high severity issues on low-scoring pillars have most impact
            impact_pts = {"high": 8, "medium": 4, "low": 2}.get(issue.severity, 1)
            steps.append(RemediationStep(
                priority=priority,
                pillar=pillar_name,
                issue=issue,
                impact=f"+{impact_pts} pts (estimated)",
            ))
            priority += 1

    return RemediationPlan(
        current_score=result.total_score,
        target_score=THRESHOLD,
        gap=THRESHOLD - result.total_score,
        steps=steps,
        estimated_total_days=sum(s.issue.effort_days for s in steps),
        can_deploy=False,
    )
