"""AssessmentRunner — orchestrates all 5 pillar scorers and produces a GapReport.

Supports evidence-based scoring when runtime data is available.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.assessment.scorers import (
    CostScorer,
    EvalScorer,
    GovernanceScorer,
    Issue,
    PillarScore,
    ReliabilityScorer,
    SecurityScorer,
)


class GapReport(BaseModel):
    """Ranked blockers by severity × effort matrix."""

    blockers: list[Issue]
    total_issues: int
    critical_count: int
    estimated_effort_days: int


class AssessmentResult(BaseModel):
    """Complete assessment output with all pillar scores and gap report."""

    total_score: int
    pillars: dict[str, PillarScore]
    gap_report: GapReport
    passed: bool  # True if total_score >= 75


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class AssessmentRunner:
    """Orchestrates all 5 pillar scorers for a project assessment."""

    def __init__(self) -> None:
        self.reliability = ReliabilityScorer()
        self.security = SecurityScorer()
        self.eval = EvalScorer()
        self.governance = GovernanceScorer()
        self.cost = CostScorer()

    def run(
        self,
        stack_json: dict,
        framework: str,
        evidence: dict | None = None,
    ) -> AssessmentResult:
        """Run all 5 scorers and produce an aggregated result with gap report.

        Parameters
        ----------
        stack_json : dict
            Static project configuration / metadata.
        framework : str
            Agent framework identifier.
        evidence : dict | None
            Optional runtime evidence dict containing keys like:
            - traces: aggregated trace stats
            - eval_runs: list of eval run results
            - connector_health: list of health records
            - ingestion_sources: list of ingestion configs
            - deployment_history: list of deployment records
            - manifest: parsed manifest data
            - audit_stats: audit log statistics
            - hitl_gate_count: number of HITL gates
        """
        pillars = {
            "reliability": self.reliability.score(stack_json, framework, evidence),
            "security": self.security.score(stack_json, framework, evidence),
            "eval": self.eval.score(stack_json, framework, evidence),
            "governance": self.governance.score(stack_json, framework, evidence),
            "cost": self.cost.score(stack_json, framework, evidence),
        }

        total_score = round(sum(p.score for p in pillars.values()) / len(pillars))

        # Collect all issues and rank by severity × effort
        all_issues: list[Issue] = []
        for pillar in pillars.values():
            all_issues.extend(pillar.issues)

        all_issues.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 99), i.effort_days))

        gap_report = GapReport(
            blockers=all_issues,
            total_issues=len(all_issues),
            critical_count=sum(1 for i in all_issues if i.severity == "high"),
            estimated_effort_days=sum(i.effort_days for i in all_issues),
        )

        return AssessmentResult(
            total_score=total_score,
            pillars=pillars,
            gap_report=gap_report,
            passed=total_score >= 75,
        )
