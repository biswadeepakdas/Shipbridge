"""Onboarding service — project creation wizard, first assessment, sample data."""

from pydantic import BaseModel

from app.assessment.runner import AssessmentResult, AssessmentRunner

import structlog

logger = structlog.get_logger()

FRAMEWORK_OPTIONS = [
    {"id": "langraph", "name": "LangGraph", "description": "Graph-based agent orchestration"},
    {"id": "crewai", "name": "CrewAI", "description": "Multi-agent crew collaboration"},
    {"id": "autogen", "name": "AutoGen", "description": "Microsoft multi-agent conversations"},
    {"id": "n8n", "name": "n8n", "description": "Workflow automation platform"},
    {"id": "custom", "name": "Custom", "description": "Custom agent framework"},
]

SAMPLE_STACK_CONFIGS: dict[str, dict] = {
    "langraph": {
        "models": ["claude-3-5-sonnet", "claude-3-haiku"],
        "tools": ["salesforce", "slack"],
        "deployment": "railway",
    },
    "crewai": {
        "models": ["claude-3-5-sonnet"],
        "tools": ["github", "linear"],
        "deployment": "railway",
    },
    "autogen": {
        "models": ["gpt-4o", "gpt-4o-mini"],
        "tools": ["airtable"],
        "deployment": "aws",
    },
    "n8n": {
        "models": ["claude-3-5-sonnet"],
        "tools": ["notion", "slack"],
        "deployment": "vercel",
    },
    "custom": {
        "models": ["claude-3-5-sonnet"],
        "tools": [],
        "deployment": "",
    },
}


class OnboardingStep(BaseModel):
    """A single step in the onboarding wizard."""

    step: int
    title: str
    description: str
    completed: bool = False


class OnboardingState(BaseModel):
    """Current onboarding state for a user."""

    steps: list[OnboardingStep]
    current_step: int
    project_id: str | None = None
    assessment_score: int | None = None
    completed: bool = False


class OnboardingResult(BaseModel):
    """Result of completing the onboarding wizard."""

    project_id: str
    project_name: str
    framework: str
    assessment_score: int
    assessment_passed: bool
    gap_report_summary: dict
    next_steps: list[str]


def get_onboarding_steps() -> list[OnboardingStep]:
    """Get the onboarding wizard steps."""
    return [
        OnboardingStep(step=1, title="Name your project", description="Give your AI agent project a name"),
        OnboardingStep(step=2, title="Select framework", description="Choose your agent framework"),
        OnboardingStep(step=3, title="Configure stack", description="Set up models, tools, and deployment"),
        OnboardingStep(step=4, title="First assessment", description="Run your first readiness assessment"),
    ]


def get_framework_options() -> list[dict]:
    """Get available framework options for the wizard."""
    return FRAMEWORK_OPTIONS


def get_sample_config(framework: str) -> dict:
    """Get a sample stack configuration for a framework."""
    return SAMPLE_STACK_CONFIGS.get(framework, SAMPLE_STACK_CONFIGS["custom"])


def run_onboarding_assessment(stack_json: dict, framework: str) -> OnboardingResult:
    """Run assessment and generate onboarding result with next steps."""
    runner = AssessmentRunner()
    result: AssessmentResult = runner.run(stack_json, framework)

    next_steps: list[str] = []
    # Generate actionable next steps from top blockers
    for issue in result.gap_report.blockers[:3]:
        next_steps.append(f"{issue.fix_hint} ({issue.effort_days}d effort)")

    if result.passed:
        next_steps.insert(0, "Your project is ready! Start a staged deployment.")
    else:
        next_steps.insert(0, f"Address {result.gap_report.critical_count} critical issue(s) to reach the 75 threshold.")

    if not any("connector" in s.lower() for s in next_steps):
        next_steps.append("Connect your first data source (Salesforce, Slack, etc.)")

    return OnboardingResult(
        project_id="",  # Set by caller
        project_name="",  # Set by caller
        framework=framework,
        assessment_score=result.total_score,
        assessment_passed=result.passed,
        gap_report_summary={
            "total_issues": result.gap_report.total_issues,
            "critical_count": result.gap_report.critical_count,
            "estimated_days": result.gap_report.estimated_effort_days,
        },
        next_steps=next_steps,
    )
