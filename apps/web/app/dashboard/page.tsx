/** Overview tab — pillar cards, score arc, readiness summary, and issue drill-down. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";
import Header from "@/components/dashboard/header";
import PillarCard from "@/components/dashboard/pillar-card";
import ScoreArc from "@/components/ui/score-arc";
import IssueList from "@/components/dashboard/issue-list";
import PageTransition from "@/components/dashboard/page-transition";

interface Issue {
  title: string;
  evidence: string;
  fix_hint: string;
  severity: string;
  effort_days: number;
}

interface PillarData {
  id: string;
  label: string;
  score: number;
  status: "ok" | "warn" | "bad";
  note: string;
  issues: Issue[];
}

const MOCK_PILLARS: PillarData[] = [
  {
    id: "reliability", label: "Reliability", score: 80, status: "ok",
    note: "Compound accuracy above threshold",
    issues: [
      { title: "Single model dependency", evidence: "Only claude-3-5-sonnet configured as primary", fix_hint: "Add a fallback model for resilience", severity: "medium", effort_days: 1 },
    ],
  },
  {
    id: "security", label: "Security", score: 60, status: "warn",
    note: "MCP endpoints need auth review",
    issues: [
      { title: "No prompt injection guard", evidence: "Agent accepts user input without injection filtering", fix_hint: "Add input sanitization and prompt injection detection", severity: "high", effort_days: 2 },
      { title: "No authentication configured", evidence: "Missing auth field in stack config", fix_hint: "Add OAuth2 or API key authentication to all endpoints", severity: "high", effort_days: 2 },
    ],
  },
  {
    id: "eval", label: "Eval", score: 75, status: "ok",
    note: "CI grader present, baseline captured",
    issues: [
      { title: "Low test coverage", evidence: "Test coverage at 65%", fix_hint: "Increase test coverage to 80%+ for production readiness", severity: "medium", effort_days: 3 },
    ],
  },
  {
    id: "governance", label: "Governance", score: 70, status: "warn",
    note: "HITL gates not configured",
    issues: [
      { title: "No human-in-the-loop gates", evidence: "No HITL approval required for high-risk actions", fix_hint: "Configure HITL gates for actions above risk threshold", severity: "high", effort_days: 3 },
      { title: "No audit trail configured", evidence: "Agent actions are not logged to immutable audit log", fix_hint: "Enable audit logging for all tool calls and LLM decisions", severity: "high", effort_days: 2 },
    ],
  },
  {
    id: "cost", label: "Cost", score: 75, status: "ok",
    note: "Model routing optimized for 3 tiers",
    issues: [
      { title: "No semantic cache", evidence: "Repeated queries hit the model every time", fix_hint: "Add semantic cache with Redis to reduce redundant LLM calls", severity: "medium", effort_days: 2 },
    ],
  },
];

// Module-level animation variants
const DRILLDOWN_VARIANTS = {
  hidden: { opacity: 0, height: 0 },
  visible: { opacity: 1, height: "auto" },
};

export default function OverviewPage() {
  const [activePillar, setActivePillar] = useState<string | null>(null);

  const handlePillarClick = useCallback((id: string) => {
    setActivePillar((prev) => (prev === id ? null : id));
  }, []);

  const totalScore = useMemo(
    () => Math.round(MOCK_PILLARS.reduce((sum, p) => sum + p.score, 0) / MOCK_PILLARS.length),
    [],
  );

  const activePillarData = useMemo(
    () => MOCK_PILLARS.find((p) => p.id === activePillar),
    [activePillar],
  );

  const gapSummary = useMemo(() => {
    const allIssues = MOCK_PILLARS.flatMap((p) => p.issues);
    return {
      total: allIssues.length,
      critical: allIssues.filter((i) => i.severity === "high").length,
      totalDays: allIssues.reduce((sum, i) => sum + i.effort_days, 0),
    };
  }, []);

  const handleDownloadPDF = useCallback(async () => {
    // In production: GET /api/v1/governance/pdf/{projectId}/download
    const projectId = "demo-project-id";
    const response = await fetch(`/api/v1/governance/pdf/${projectId}/download`);
    if (response.ok) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `shipbridge-compliance-${projectId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    }
  }, []);

  return (
    <PageTransition pageKey="overview">
      <Header
        title="Overview"
        subtitle="Production readiness assessment"
        actions={
          <button
            type="button"
            onClick={handleDownloadPDF}
            style={{
              padding: "8px 14px", borderRadius: "6px",
              border: `1px solid ${T.b2}`, backgroundColor: "transparent",
              color: T.t2, fontFamily: FONT.ui, fontSize: 12,
              cursor: "pointer", display: "flex", alignItems: "center", gap: "6px",
            }}
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
              <path d="M6.5 1v8M3.5 6.5l3 3 3-3" />
              <path d="M1 10.5v1a.5.5 0 00.5.5h10a.5.5 0 00.5-.5v-1" />
            </svg>
            Compliance PDF
          </button>
        }
      />
      <div style={{ padding: "24px" }}>
        {/* Score + summary row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "32px",
            marginBottom: "24px",
            padding: "24px",
            backgroundColor: T.s1,
            borderRadius: "8px",
            border: `1px solid ${T.b0}`,
          }}
        >
          <ScoreArc score={totalScore} size={140} />
          <div style={{ flex: 1 }}>
            <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, margin: 0 }}>
              {totalScore >= 75 ? "Ready for production" : "Not yet ready"}
            </h2>
            <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t2, marginTop: 4 }}>
              {totalScore >= 75
                ? "All pillars meet the minimum threshold. Proceed with staged deployment."
                : `Score ${totalScore}/100 — address blockers in the gap report to reach 75.`}
            </p>
            {/* Gap summary stats */}
            <div style={{ display: "flex", gap: "20px", marginTop: 12 }}>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: gapSummary.critical > 0 ? T.danger : T.ok }}>
                  {gapSummary.critical}
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  critical
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: T.t1 }}>
                  {gapSummary.total}
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  total issues
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: T.t2 }}>
                  {gapSummary.totalDays}d
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  est. effort
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Pillar cards grid */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "16px" }}>
          {MOCK_PILLARS.map((pillar) => (
            <PillarCard
              key={pillar.id}
              pillar={pillar}
              isActive={activePillar === pillar.id}
              onClick={handlePillarClick}
            />
          ))}
        </div>

        {/* Drill-down panel */}
        <AnimatePresence>
          {activePillarData && (
            <motion.div
              key={activePillarData.id}
              variants={DRILLDOWN_VARIANTS}
              initial="hidden"
              animate="visible"
              exit="hidden"
              transition={{ duration: 0.25 }}
              style={{
                overflow: "hidden",
                backgroundColor: T.s1,
                borderRadius: "8px",
                border: `1px solid ${T.b1}`,
                padding: "16px 20px",
              }}
            >
              <IssueList
                issues={activePillarData.issues}
                pillarLabel={activePillarData.label}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
